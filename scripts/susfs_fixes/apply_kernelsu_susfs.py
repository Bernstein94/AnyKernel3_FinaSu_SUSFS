#!/usr/bin/env python3
"""为原生 KernelSU (tiann/KernelSU) 添加 SUSFS 支持。

tiann/KernelSU 结构随提交而变化，本脚本采用宽松匹配与多候选回退，
尽量在上游结构变动时仍能正确集成 SUSFS：

- kernel/core/init.c: 添加 #include <linux/susfs.h>，替换 hook 初始化为 susfs_init()，
  守卫已从 Kbuild 移除的 hook 清理函数。
- kernel/Kconfig: 插入 KSU_SUSFS 菜单（嵌套在 menu "KernelSU" 内）。
- kernel/Kbuild: 移除与 SUSFS 冲突的 hook 编译单元。

simonpunk/susfs4ksu 的补丁针对 flat kernel/ksu.c，与 tiann/KernelSU 结构不匹配，
故直接修改源码。如果无法自动集成，则返回非零退出码以便上层回退到手工 sed。
"""

import sys
from pathlib import Path

KSU_KERNEL = Path("KernelSU/kernel")

# ---------------------------------------------------------------------------
# 小工具：按“语义行”匹配，忽略缩进与尾随空格/分号前后空格
# ---------------------------------------------------------------------------

def _norm(line: str) -> str:
    """归一化一行：去首尾空白，统一分号周围空格，用于比较代码语句是否相同。"""
    return " ".join(line.strip().split())


def _strip_paren_space(norm: str) -> str:
    """把 'foo ();' 归一为 'foo();'，兼容上游偶尔在括号前加空格的写法。"""
    return norm.replace(" (", "(").replace(") ", ")")


def _line_matches(line: str, target: str) -> bool:
    """判断一行代码（忽略缩进）是否等于目标语句。"""
    n = _strip_paren_space(_norm(line))
    t = _strip_paren_space(_norm(target))
    return n == t


def _indent(line: str) -> str:
    """提取行首缩进。"""
    return line[: len(line) - len(line.lstrip())]


# ---------------------------------------------------------------------------
# Kconfig：插入 KSU_SUSFS 菜单
# ---------------------------------------------------------------------------

def _find_endmenu_idx(lines: list[str]) -> int:
    """在 Kconfig 行中找到最外层 endmenu 的索引；找不到返回 -1。"""
    for i, line in enumerate(lines):
        if _norm(line) == "endmenu":
            return i
    return -1


_SUSFS_MENU = [
    'menu "KernelSU - SUSFS"',
    'config KSU_SUSFS',
    '\tbool "KernelSU addon - SUSFS"',
    '\tdepends on KSU',
    '\tdefault y',
    '\thelp',
    '\t  Patch and Enable SUSFS to kernel with KernelSU',
    '',
    'config KSU_SUSFS_SUS_PATH',
    '\tbool "Enable to hide suspicious path"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_SUS_MOUNT',
    '\tbool "Enable to hide suspicious mounts"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_SUS_KSTAT',
    '\tbool "Enable to spoof suspicious kstat"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_SPOOF_UNAME',
    '\tbool "Enable to spoof uname"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_ENABLE_LOG',
    '\tbool "Enable logging susfs log to kernel"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS',
    '\tbool "Hide KSU SUSFS symbols"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG',
    '\tbool "Spoof cmdline or bootconfig"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_SUS_MAP',
    '\tbool "Enable SUS_MAP"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_OPEN_REDIRECT',
    '\tbool "Enable open redirect"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    '',
    'config KSU_SUSFS_PRIORITY_UID_FILTER',
    '\tbool "Enable priority UID filter"',
    '\tdepends on KSU_SUSFS',
    '\tdefault y',
    'endmenu',
]


def modify_kconfig():
    """在 Kconfig 中添加完整的 KSU_SUSFS 菜单。"""
    kconfig = KSU_KERNEL / "Kconfig"
    if not kconfig.exists():
        print(f"WARNING: {kconfig} not found, skipping SUSFS menu for KernelSU", file=sys.stderr)
        return False
    s = kconfig.read_text(encoding="utf-8")
    if "config KSU_SUSFS" in s:
        print("Kconfig: SUSFS menu already present")
        return True

    lines = s.split("\n")
    idx = _find_endmenu_idx(lines)
    if idx < 0:
        print("WARNING: endmenu not found in Kconfig, skipping SUSFS menu", file=sys.stderr)
        return False

    # 在 endmenu 之前插入 SUSFS 子菜单（嵌套于 menu "KernelSU" 内）
    insert_lines = list(_SUSFS_MENU) + [""]
    lines[idx:idx] = insert_lines
    kconfig.write_text("\n".join(lines), encoding="utf-8")
    print("Kconfig: SUSFS menu added with all config options")
    return True


# ---------------------------------------------------------------------------
# init.c：添加 SUSFS 支持
# ---------------------------------------------------------------------------

def _add_susfs_include(s: str):
    """在 init.c 中加入 #include <linux/susfs.h>，尝试多个可能的调度头文件锚点。"""
    markers = [
        "#include <linux/sched.h>",
        "#include <linux/sched/task.h>",
        "#include <linux/sched/signal.h>",
        "#include <linux/sched/wake_q.h>",
        "#include <linux/sched/cputime.h>",
    ]
    if "#include <linux/susfs.h>" in s:
        return s, True, "include already present"

    for marker in markers:
        if marker in s:
            s = s.replace(marker, marker + "\n#include <linux/susfs.h>", 1)
            return s, True, f"added after {marker}"

    # 回退：任何 #include <linux/*.h> 行之后插入
    import re
    m = re.search(r"#include <linux/[^>]+\.h>\n", s)
    if m:
        end = m.end()
        s = s[:end] + "#include <linux/susfs.h>\n" + s[end:]
        return s, True, "added after first linux include"

    return s, False, "no suitable include anchor found"


def _replace_hook_inits(s: str):
    """把 hook 初始化调用替换为受 CONFIG_KSU_SUSFS 保护的 susfs_init()。"""
    hook_calls = (
        "ksu_syscall_hook_manager_init();",
        "ksu_syscall_hook_init();",
        "ksu_lsm_hook_init();",
    )
    changed = False
    lines = s.split("\n")
    new_lines = []
    for line in lines:
        n = _strip_paren_space(_norm(line))
        replaced = False
        for hc in hook_calls:
            if n == _strip_paren_space(_norm(hc)):
                indent = _indent(line)
                new_lines.append(f"{indent}#if defined(CONFIG_KSU_SUSFS)")
                new_lines.append(f"{indent}    susfs_init();")
                new_lines.append(f"{indent}#endif")
                replaced = True
                changed = True
                break
        if not replaced:
            new_lines.append(line)
    return "\n".join(new_lines), changed


def _insert_susfs_init_in_func(s: str):
    """若 susfs_init() 仍未出现，在 kernelsu_init() 函数体末尾（return 0; 前）插入。"""
    if "susfs_init()" in s:
        return s, False, "susfs_init() already present"

    func_patterns = ("kernelsu_init(", "ksu_init(", "init_kernelsu(")
    for fp in func_patterns:
        idx = s.find(fp)
        if idx < 0:
            continue
        ret_idx = s.find("return 0;", idx)
        if ret_idx < 0:
            continue
        insertion = (
            "\n    #ifdef CONFIG_KSU_SUSFS\n"
            "    susfs_init();\n"
            "    #endif\n"
        )
        s = s[:ret_idx] + insertion + s[ret_idx:]
        return s, True, f"inserted susfs_init() before return 0; in {fp}"

    return s, False, "kernelsu_init() function not found"


def _guard_removed_hook_calls(s: str):
    """守卫已从 Kbuild 移除的 hook 清理函数，仅在未启用 SUSFS 时调用。

    这些函数的 .o 已被 modify_kbuild() 移出编译，若 SUSFS 启用则不应再调用，
    否则会造成 undefined symbol 链接错误。
    """
    guarded_calls = (
        "ksu_lsm_hook_init();",
        "ksu_syscall_hook_manager_exit();",
        "ksu_lsm_hook_exit();",
    )
    changed = False
    lines = s.split("\n")
    new_lines = []

    for line in lines:
        n = _strip_paren_space(_norm(line))
        match = None
        for gc in guarded_calls:
            if n == _strip_paren_space(_norm(gc)):
                match = gc
                break

        if match is None:
            new_lines.append(line)
            continue

        # 如果上一行已经是对应的 #ifndef CONFIG_KSU_SUSFS，说明已守卫，跳过
        if new_lines and _norm(new_lines[-1]) == "#ifndef CONFIG_KSU_SUSFS":
            new_lines.append(line)
            continue

        indent = _indent(line)
        new_lines.append(f"{indent}#ifndef CONFIG_KSU_SUSFS")
        new_lines.append(line)
        new_lines.append(f"{indent}#endif")
        changed = True

    return "\n".join(new_lines), changed


def modify_init_c():
    """在 init.c 中添加 SUSFS 支持。"""
    init_c = KSU_KERNEL / "core" / "init.c"
    if not init_c.exists():
        print(f"ERROR: {init_c} not found, cannot integrate SUSFS for KernelSU", file=sys.stderr)
        return False
    s = init_c.read_text(encoding="utf-8")
    changed = False

    # 步骤1：添加 #include <linux/susfs.h>
    s, inc_ok, inc_msg = _add_susfs_include(s)
    if inc_ok:
        changed = True
        print(f"init.c: {inc_msg}")
    else:
        print(f"WARNING: {inc_msg}", file=sys.stderr)

    # 步骤2：把 hook 初始化替换为受 CONFIG_KSU_SUSFS 保护的 susfs_init()
    s, hook_ok = _replace_hook_inits(s)
    if hook_ok:
        changed = True
        print("init.c: replaced hook init calls with susfs_init()")

    # 步骤3：若仍未出现 susfs_init()，在 kernelsu_init() 内插入
    s, ins_ok, ins_msg = _insert_susfs_init_in_func(s)
    if ins_ok:
        changed = True
        print(f"init.c: {ins_msg}")
    else:
        print(f"init.c: {ins_msg}")

    # 步骤4：守卫已从 Kbuild 移除的 hook 清理函数
    s, guard_ok = _guard_removed_hook_calls(s)
    if guard_ok:
        changed = True
        print("init.c: guarded removed-hook cleanup calls with #ifndef CONFIG_KSU_SUSFS")

    if changed:
        init_c.write_text(s, encoding="utf-8")
        print("init.c: SUSFS support added")
        return True
    elif "susfs_init()" in s and "#include <linux/susfs.h>" in s:
        print("init.c: SUSFS support already present")
        return True
    else:
        print("init.c: SUSFS support could not be added", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Kbuild：移除旧 hook 编译单元
# ---------------------------------------------------------------------------

_HOOK_OBJS = (
    "kernelsu-objs += hook/lsm_hook.o",
    # setuid_hook.o 保留：su/resuid 逻辑与 SUSFS 替换的 hook 机制无关，
    # 与 upstream 10_enable_susfs_for_ksu.patch 保持一致。
    "kernelsu-objs += hook/syscall_event_bridge.o",
    "kernelsu-objs += hook/syscall_hook_manager.o",
    "kernelsu-objs += hook/tp_marker.o",
    "kernelsu-objs += hook/arm64/patch_memory.o",
    "kernelsu-objs += hook/arm64/syscall_hook.o",
    "kernelsu-objs += hook/x86_64/patch_memory.o",
    "kernelsu-objs += hook/x86_64/syscall_hook.o",
    "kernelsu-objs += hook/riscv64/patch_memory.o",
    "kernelsu-objs += hook/riscv64/syscall_hook.o",
)


def modify_kbuild():
    """在 Kbuild 中移除与 SUSFS 冲突的 hook 编译单元。

    与 upstream 10_enable_susfs_for_ksu.patch 保持一致：移除所有与 SUSFS
    冲突的 hook 编译单元，包括顶层和 ifeq 块内的 arch-specific 行。
    """
    kbuild = KSU_KERNEL / "Kbuild"
    if not kbuild.exists():
        print(f"WARNING: {kbuild} not found, skipping Kbuild cleanup", file=sys.stderr)
        return True
    s = kbuild.read_text(encoding="utf-8")
    changed = False
    lines = s.split("\n")
    new_lines = []
    for line in lines:
        n = _norm(line)
        if any(n == _norm(obj) for obj in _HOOK_OBJS):
            changed = True
            continue  # 移除该行
        new_lines.append(line)
    if changed:
        kbuild.write_text("\n".join(new_lines), encoding="utf-8")
        print("Kbuild: old hook objects removed")
    else:
        print("Kbuild: no old hook objects found")
    return True


def main():
    kconfig_ok = modify_kconfig()
    init_ok = modify_init_c()
    kbuild_ok = modify_kbuild()

    # init.c 是关键：没有 susfs_init() 就没有 SUSFS
    if not init_ok:
        print("ERROR: 无法在 KernelSU init.c 中集成 SUSFS，构建将中断", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
