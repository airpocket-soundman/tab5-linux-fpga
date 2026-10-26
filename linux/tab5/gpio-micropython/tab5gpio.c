/* SPDX-License-Identifier: GPL-2.0-only */
/* Native MicroPython 1.22.2 user module, synchronous Linux GPIO line ownership. */
#include "py/runtime.h"
#include "tab5_gpio.h"
#include <errno.h>
#include <limits.h>

#if !MICROPY_ENABLE_FINALISER
#error "tab5gpio requires MICROPY_ENABLE_FINALISER for descriptor cleanup"
#endif

typedef struct {
    mp_obj_base_t base;
    struct tab5_gpio line;
} tab5_pin_obj_t;
static const mp_obj_type_t tab5_pin_type;

static tab5_pin_obj_t *pin_self(mp_obj_t object) {
    if (!mp_obj_is_exact_type(object, &tab5_pin_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected tab5gpio.Pin"));
    }
    return MP_OBJ_TO_PTR(object);
}

static mp_int_t strict_integer(mp_obj_t object) {
    /* Reject bool, float, str and arbitrary __int__/__index__ before any I/O. */
    if (!mp_obj_is_int(object)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected integer (not bool)"));
    }
    return mp_obj_get_int(object);
}

static int binary_value(mp_obj_t object) {
    mp_int_t value = strict_integer(object);
    if (value != 0 && value != 1) {
        mp_raise_ValueError(MP_ERROR_TEXT("expected 0 or 1"));
    }
    return (int)value;
}

static mp_obj_t pin_make_new(const mp_obj_type_t *type, size_t n_args,
                             size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_id, ARG_mode, ARG_value };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_id, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_mode, MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_SMALL_INT(0)} },
        { MP_QSTR_value, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_SMALL_INT(0)} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed), allowed, args);
    mp_int_t pin = strict_integer(args[ARG_id].u_obj);
    int output = binary_value(args[ARG_mode].u_obj);
    int initial = binary_value(args[ARG_value].u_obj);
    if (pin < 0 || (mp_uint_t)pin > UINT_MAX) {
        mp_raise_ValueError(MP_ERROR_TEXT("pin number out of range"));
    }
    if (!output && initial) {
        mp_raise_ValueError(MP_ERROR_TEXT("input cannot set initial output"));
    }
    if (!tab5_gpio_pin_allowed((unsigned)pin)) {
        mp_raise_OSError(EPERM);
    }
    /* Allocate finalizable storage BEFORE obtaining an fd. Initialise even on
     * failed construction so collection cannot close a default/reused fd. */
    tab5_pin_obj_t *self = m_new_obj_with_finaliser(tab5_pin_obj_t);
    self->base.type = type;
    self->line = (struct tab5_gpio)TAB5_GPIO_INITIALIZER;
    if (tab5_gpio_open(&self->line, (unsigned)pin, output, initial) < 0) {
        mp_raise_OSError(errno);
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t pin_value(size_t n_args, const mp_obj_t *args) {
    tab5_pin_obj_t *self = pin_self(args[0]);
    if (n_args == 1) {
        int result = tab5_gpio_get(&self->line);
        if (result < 0) mp_raise_OSError(errno);
        return MP_OBJ_NEW_SMALL_INT(result);
    }
    int value = binary_value(args[1]);
    if (tab5_gpio_set(&self->line, value) < 0) mp_raise_OSError(errno);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(pin_value_obj, 1, 2, pin_value);

static mp_obj_t pin_on(mp_obj_t object) {
    tab5_pin_obj_t *self = pin_self(object);
    if (tab5_gpio_set(&self->line, 1) < 0) mp_raise_OSError(errno);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_on_obj, pin_on);
static mp_obj_t pin_off(mp_obj_t object) {
    tab5_pin_obj_t *self = pin_self(object);
    if (tab5_gpio_set(&self->line, 0) < 0) mp_raise_OSError(errno);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_off_obj, pin_off);

static mp_obj_t pin_deinit(mp_obj_t object) {
    tab5_pin_obj_t *self = pin_self(object);
    if (tab5_gpio_close(&self->line) < 0) mp_raise_OSError(errno);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_deinit_obj, pin_deinit);

static mp_obj_t pin_finalizer(mp_obj_t object) {
    tab5_pin_obj_t *self = pin_self(object);
    /* close() clears ownership first. Do not retry EINTR: fd may be reused. */
    (void)tab5_gpio_close(&self->line);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_finalizer_obj, pin_finalizer);

static mp_obj_t pin_enter(mp_obj_t object) {
    tab5_pin_obj_t *self = pin_self(object);
    if (self->line.fd < 0) mp_raise_OSError(EBADF);
    return object;
}
static MP_DEFINE_CONST_FUN_OBJ_1(pin_enter_obj, pin_enter);
static mp_obj_t pin_exit(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    pin_deinit(args[0]);
    return mp_const_false; /* propagate the with-body exception */
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(pin_exit_obj, 4, 4, pin_exit);

static const mp_rom_map_elem_t pin_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_IN), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_OUT), MP_ROM_INT(1) },
    { MP_ROM_QSTR(MP_QSTR_value), MP_ROM_PTR(&pin_value_obj) },
    { MP_ROM_QSTR(MP_QSTR_on), MP_ROM_PTR(&pin_on_obj) },
    { MP_ROM_QSTR(MP_QSTR_off), MP_ROM_PTR(&pin_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&pin_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&pin_finalizer_obj) },
    { MP_ROM_QSTR(MP_QSTR___enter__), MP_ROM_PTR(&pin_enter_obj) },
    { MP_ROM_QSTR(MP_QSTR___exit__), MP_ROM_PTR(&pin_exit_obj) },
};
static MP_DEFINE_CONST_DICT(pin_locals, pin_locals_table);
static MP_DEFINE_CONST_OBJ_TYPE(tab5_pin_type, MP_QSTR_Pin, MP_TYPE_FLAG_NONE,
    make_new, pin_make_new, locals_dict, &pin_locals);

#if TAB5_GPIO_TEST_BACKEND
extern void tab5_gpio_test_stats(unsigned out[4]);
extern void tab5_gpio_test_fail_close(void);
static mp_obj_t test_stats(void) {
    unsigned values[4]; mp_obj_t items[4];
    tab5_gpio_test_stats(values);
    for (size_t i = 0; i < 4; ++i) items[i] = mp_obj_new_int_from_uint(values[i]);
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(test_stats_obj, test_stats);
static mp_obj_t test_fail_close(void) {
    tab5_gpio_test_fail_close();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(test_fail_close_obj, test_fail_close);
#endif

static const mp_rom_map_elem_t module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_tab5gpio) },
    { MP_ROM_QSTR(MP_QSTR_Pin), MP_ROM_PTR(&tab5_pin_type) },
#if TAB5_GPIO_TEST_BACKEND
    { MP_ROM_QSTR(MP_QSTR__test_stats), MP_ROM_PTR(&test_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR__test_fail_close), MP_ROM_PTR(&test_fail_close_obj) },
#endif
};
static MP_DEFINE_CONST_DICT(module_globals, module_globals_table);
const mp_obj_module_t tab5gpio_module = {
    .base = { &mp_type_module }, .globals = (mp_obj_dict_t *)&module_globals,
};
MP_REGISTER_MODULE(MP_QSTR_tab5gpio, tab5gpio_module);
