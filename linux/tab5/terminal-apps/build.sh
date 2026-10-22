#!/usr/bin/env bash
# Build only a static NOMMU userspace toolchain and genuine terminal apps.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$script_dir/../../.." && pwd)
work=${TAB5_APPS_WORK:-"$repo/work/terminal-apps"}
source_dir="$work/buildroot-source"
output="$work/br-output"
download="$work/downloads"
artifacts="$repo/artifacts/terminal-apps"
sdk_artifacts="$repo/artifacts/terminal-sdk"
buildroot_commit=c49ae7216786d3cb62a8e8de5556007b4b539233
mkdir -p "$work" "$artifacts" "$sdk_artifacts" "$download"
export LC_ALL=C
# Do not inherit an interactive cross environment from ESP-IDF or a host SDK.
unset CROSS_COMPILE ARCH LD_LIBRARY_PATH
brmake() { make -C "$source_dir" O="$output" BR2_DL_DIR="$download" "$@"; }

prepare() {
    if [[ ! -d "$source_dir/.git" ]]; then
        git clone --depth 1 --branch 2025.02.15 \
            https://github.com/buildroot/buildroot.git "$source_dir"
    fi
    [[ $(git -C "$source_dir" rev-parse HEAD) == "$buildroot_commit" ]] || {
        echo 'Unexpected Buildroot source commit' >&2; exit 1;
    }
    # Restore just the two package metadata files this script customizes.
    git -C "$source_dir" restore --source HEAD -- package/vim/Config.in package/vim/vim.mk
    python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
config = root / 'package/vim/Config.in'
text = config.read_text()
old = '\tdepends on BR2_USE_MMU # uses fork()\n'
if text.count(old) != 1:
    raise SystemExit('Unexpected Vim MMU dependency; re-audit the package')
config.write_text(text.replace(old, ''))
recipe = root / 'package/vim/vim.mk'
text = recipe.read_text()
marker = '$(eval $(autotools-package))'
if text.count(marker) != 1:
    raise SystemExit('Unexpected Vim package recipe')
extra = '''# Tab5 tiny editor: no job/channel/GUI or shell process creation.
VIM_CONF_OPTS += --with-features=tiny --enable-multibyte --disable-nls --disable-netbeans --disable-channel --disable-terminal
VIM_CONF_ENV += CFLAGS="$(TARGET_CFLAGS) -DUSE_SYSTEM -DTAB5_VIM_NO_SHELL" ac_cv_func_fork=no ac_cv_func_vfork=yes

'''
recipe.write_text(text.replace(marker, extra + marker))
PY
    # A complete output cache retains the expensive toolchain. Rebuild app
    # packages after each restore so source-patch changes cannot reuse old apps.
    if [[ -f "$output/.config" ]]; then
        brmake vim-dirclean nano-dirclean sl-dirclean
    fi
    brmake BR2_DEFCONFIG="$script_dir/defconfig" defconfig
    "$source_dir/utils/config" --file "$output/.config" \
        --set-str BR2_GLOBAL_PATCH_DIR "$script_dir/patches"
    brmake olddefconfig
    for option in BR2_RISCV_32 BR2_RISCV_ABI_ILP32 BR2_BINFMT_FLAT \
        BR2_STATIC_LIBS BR2_TOOLCHAIN_BUILDROOT_UCLIBC BR2_USE_WCHAR \
        BR2_PACKAGE_VIM BR2_PACKAGE_NANO BR2_PACKAGE_NANO_TINY BR2_PACKAGE_SL \
        BR2_PACKAGE_NCURSES_WCHAR; do
        grep -Fxq "$option=y" "$output/.config" || {
            echo "Required configuration lost: $option" >&2; exit 1;
        }
    done
    if grep -Eq '^BR2_(USE_MMU|RISCV_USE_MMU|RISCV_ISA_RVF|RISCV_ISA_RVD)=y$' "$output/.config"; then
        echo 'MMU or floating-point ISA unexpectedly enabled' >&2; exit 1
    fi
    cp "$output/.config" "$artifacts/buildroot.config"
    {
        printf 'source_commit=%s\n' "${GITHUB_SHA:-$(git -C "$repo" rev-parse HEAD)}"
        printf 'buildroot_commit=%s\n' "$buildroot_commit"
        printf 'abi=rv32imac-ilp32-nommu-static-bFLT\n'
        printf 'baseline_run=39729147095\nrootfs_offset=0x810000\n'
        printf 'vim_shell_commands=disabled\nnano=tiny\n'
        git -C "$source_dir" diff -- package/vim/Config.in package/vim/vim.mk
    } > "$artifacts/build-info.txt"
}

toolchain() { brmake -j"${TAB5_APPS_JOBS:-$(nproc)}" toolchain; }

sdk() {
    cp "$output/.config" "$sdk_artifacts/buildroot.config"
    cp "$artifacts/build-info.txt" "$sdk_artifacts/build-info.txt"
    bash "$script_dir/package-sdk.sh" "$source_dir" "$output" "$sdk_artifacts"
}

apps() {
    test -f "$script_dir/patches/vim/0001-tab5-tiny-nommu-no-shell.patch"
    brmake -j"${TAB5_APPS_JOBS:-$(nproc)}" ncurses nano sl vim
    "$output/host/bin/riscv32-buildroot-linux-uclibc-gcc" \
        -std=c11 -Os -fPIC -static -march=rv32imac_zicsr_zifencei -mabi=ilp32 \
        -D_LARGEFILE_SOURCE -D_LARGEFILE64_SOURCE -D_FILE_OFFSET_BITS=64 \
        '-Wl,-elf2flt=-r -s32768' \
        -o "$output/target/usr/bin/fpga-link" "$repo/tools/fpga-link/fpga_link.c"
    python3 "$script_dir/package.py" "$output" "$artifacts"
    mkdir -p "$artifacts/licenses"
    cp "$source_dir/package/vim/vim.mk" "$source_dir/package/nano/nano.mk" \
       "$source_dir/package/sl/sl.mk" "$source_dir/package/ncurses/ncurses.mk" \
       "$source_dir/package/uclibc/uclibc.mk" "$artifacts/licenses/"
    find "$output/build" -maxdepth 2 -type f \
        \( -name COPYING -o -name COPYING.LIB -o -name LICENSE \) \
        -print | while IFS= read -r license; do
            package=$(basename -- "$(dirname -- "$license")")
            cp "$license" "$artifacts/licenses/$package-$(basename -- "$license")"
        done
}

case ${1:-all} in
    prepare) prepare ;;
    toolchain) toolchain ;;
    sdk) sdk ;;
    apps) apps ;;
    all) prepare; toolchain; sdk; apps ;;
    *) echo "Usage: $0 [prepare|toolchain|sdk|apps|all]" >&2; exit 2 ;;
esac
