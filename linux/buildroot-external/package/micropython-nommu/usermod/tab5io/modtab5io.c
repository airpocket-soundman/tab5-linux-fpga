/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 tab5-linux-fpga contributors
 */
#include "py/runtime.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/gpio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#if !MICROPY_ENABLE_FINALISER
#error tab5io requires GC finalizers for GPIO descriptor cleanup
#endif

typedef struct {
	mp_obj_base_t base;
	int fd;
	bool output;
} tab5_pin_t;

static void check_live(tab5_pin_t *self)
{ if (self->fd<0) mp_raise_ValueError(MP_ERROR_TEXT("Pin is deinitialized")); }

static mp_obj_t pin_new(const mp_obj_type_t *type,size_t n_args,size_t n_kw,const mp_obj_t *args)
{
	enum { ARG_chip, ARG_offset, ARG_mode, ARG_value };
	static const mp_arg_t allowed[]={
		{MP_QSTR_chip,MP_ARG_REQUIRED|MP_ARG_OBJ,{.u_obj=MP_OBJ_NULL}},
		{MP_QSTR_offset,MP_ARG_REQUIRED|MP_ARG_INT,{.u_int=0}},
		{MP_QSTR_mode,MP_ARG_INT,{.u_int=0}},
		{MP_QSTR_value,MP_ARG_KW_ONLY|MP_ARG_INT,{.u_int=0}},
	};
	mp_arg_val_t values[MP_ARRAY_SIZE(allowed)];
	struct gpiochip_info chip={0};
	struct gpio_v2_line_request req={0};
	int fd,saved;
	tab5_pin_t *self;
	mp_arg_parse_all_kw_array(n_args,n_kw,args,MP_ARRAY_SIZE(allowed),allowed,values);
	const char *path=mp_obj_str_get_str(values[ARG_chip].u_obj);
	if (values[ARG_offset].u_int<0 || (mp_uint_t)values[ARG_offset].u_int>UINT_MAX ||
	    values[ARG_mode].u_int<0 || values[ARG_mode].u_int>1 ||
	    values[ARG_value].u_int<0 || values[ARG_value].u_int>1) {
		mp_raise_ValueError(MP_ERROR_TEXT("Invalid offset, mode or value"));
	}
	/* Allocate before acquiring a kernel resource; GC finalizes abandoned Pins. */
	self=m_new_obj_with_finaliser(tab5_pin_t);
	self->base.type=type;
	self->fd=-1; self->output=values[ARG_mode].u_int==1;
	fd=open(path,O_RDONLY|O_CLOEXEC);
	if (fd<0) mp_raise_OSError(errno);
	if (ioctl(fd,GPIO_GET_CHIPINFO_IOCTL,&chip)<0) goto error;
	if ((mp_uint_t)values[ARG_offset].u_int>=chip.lines) {
		close(fd); mp_raise_ValueError(MP_ERROR_TEXT("Offset outside chip"));
	}
	req.offsets[0]=values[ARG_offset].u_int;
	req.num_lines=1; strcpy(req.consumer,"micropython-tab5");
	req.config.flags=self->output ? GPIO_V2_LINE_FLAG_OUTPUT : GPIO_V2_LINE_FLAG_INPUT;
	if (self->output) {
		req.config.num_attrs=1;
		req.config.attrs[0].mask=1;
		req.config.attrs[0].attr.id=GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
		req.config.attrs[0].attr.values=values[ARG_value].u_int;
	}
	if (ioctl(fd,GPIO_V2_GET_LINE_IOCTL,&req)<0) goto error;
	close(fd); self->fd=req.fd;
	return MP_OBJ_FROM_PTR(self);
error:
	saved=errno; close(fd); mp_raise_OSError(saved);
}

static mp_obj_t pin_deinit(mp_obj_t object)
{
	tab5_pin_t *self=MP_OBJ_TO_PTR(object);
	if (self->fd>=0) { close(self->fd); self->fd=-1; }
	return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_deinit_obj,pin_deinit);

static mp_obj_t pin_value(size_t n_args,const mp_obj_t *args)
{
	tab5_pin_t *self=MP_OBJ_TO_PTR(args[0]);
	struct gpio_v2_line_values value={.mask=1};
	int level=0;
	/* Convert first: user conversion may release this object or raise. */
	if (n_args==2) level=mp_obj_get_int(args[1]);
	check_live(self);
	if (n_args==1) {
		if (ioctl(self->fd,GPIO_V2_LINE_GET_VALUES_IOCTL,&value)<0) mp_raise_OSError(errno);
		return mp_obj_new_int(value.bits&1);
	}
	if (!self->output) mp_raise_ValueError(MP_ERROR_TEXT("Pin is input"));
	if (level!=0 && level!=1) mp_raise_ValueError(MP_ERROR_TEXT("Value must be 0 or 1"));
	value.bits=level;
	if (ioctl(self->fd,GPIO_V2_LINE_SET_VALUES_IOCTL,&value)<0) mp_raise_OSError(errno);
	return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(pin_value_obj,1,2,pin_value);

static mp_obj_t pin_on(mp_obj_t self)
{ mp_obj_t args[]={self,MP_OBJ_NEW_SMALL_INT(1)}; return pin_value(2,args); }
static MP_DEFINE_CONST_FUN_OBJ_1(pin_on_obj,pin_on);
static mp_obj_t pin_off(mp_obj_t self)
{ mp_obj_t args[]={self,MP_OBJ_NEW_SMALL_INT(0)}; return pin_value(2,args); }
static MP_DEFINE_CONST_FUN_OBJ_1(pin_off_obj,pin_off);
static mp_obj_t pin_enter(mp_obj_t object)
{ check_live(MP_OBJ_TO_PTR(object)); return object; }
static MP_DEFINE_CONST_FUN_OBJ_1(pin_enter_obj,pin_enter);
static mp_obj_t pin_exit(size_t n_args,const mp_obj_t *args)
{ (void)n_args; pin_deinit(args[0]); return mp_const_false; }
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(pin_exit_obj,4,4,pin_exit);

static const mp_rom_map_elem_t pin_locals_table[]={
	{MP_ROM_QSTR(MP_QSTR_IN),MP_ROM_INT(0)},
	{MP_ROM_QSTR(MP_QSTR_OUT),MP_ROM_INT(1)},
	{MP_ROM_QSTR(MP_QSTR_value),MP_ROM_PTR(&pin_value_obj)},
	{MP_ROM_QSTR(MP_QSTR_on),MP_ROM_PTR(&pin_on_obj)},
	{MP_ROM_QSTR(MP_QSTR_off),MP_ROM_PTR(&pin_off_obj)},
	{MP_ROM_QSTR(MP_QSTR_deinit),MP_ROM_PTR(&pin_deinit_obj)},
	{MP_ROM_QSTR(MP_QSTR___del__),MP_ROM_PTR(&pin_deinit_obj)},
	{MP_ROM_QSTR(MP_QSTR___enter__),MP_ROM_PTR(&pin_enter_obj)},
	{MP_ROM_QSTR(MP_QSTR___exit__),MP_ROM_PTR(&pin_exit_obj)},
};
static MP_DEFINE_CONST_DICT(pin_locals,pin_locals_table);
MP_DEFINE_CONST_OBJ_TYPE(tab5_pin_type,MP_QSTR_Pin,MP_TYPE_FLAG_NONE,
	make_new,pin_new,locals_dict,&pin_locals);
static const mp_rom_map_elem_t globals_table[]={
	{MP_ROM_QSTR(MP_QSTR___name__),MP_ROM_QSTR(MP_QSTR_tab5io)},
	{MP_ROM_QSTR(MP_QSTR_Pin),MP_ROM_PTR(&tab5_pin_type)},
};
static MP_DEFINE_CONST_DICT(globals,globals_table);
const mp_obj_module_t tab5io_module={.base={&mp_type_module},.globals=(mp_obj_dict_t *)&globals};
MP_REGISTER_MODULE(MP_QSTR_tab5io,tab5io_module);
