#!/usr/bin/env python3
"""Patch p4a's run_pymodules_install so the build venv's pip accepts
android-tagged wheels.

Background: p4a resolves pure-Python requirements with
`pip install --dry-run --platform=android_24_<arch> ...` and may pick
platform-specific wheels (e.g.
charset_normalizer-3.5.2-cp314-cp314-android_24_arm64_v8a.whl). It then
installs them with the *host* pip (`venv/bin/pip install --target ...`),
which rejects them with "not a supported wheel on this platform" because
the host platform tags don't match. Passing the same --platform tags the
resolver used (per-arch) makes pip accept them.

Idempotent: exits 0 immediately if already patched. Fails loudly if the
expected code isn't found, so a p4a change never wastes a full build.
"""

import sys

P4A_BUILD_PY = (
    ".buildozer/android/platform/python-for-android"
    "/pythonforandroid/build.py"
)
MARKER = "IVAagent patch: accept android wheels"


def main() -> int:
    try:
        src = open(P4A_BUILD_PY).read()
    except FileNotFoundError:
        print("p4a build.py not found at %s" % P4A_BUILD_PY, file=sys.stderr)
        return 1

    if MARKER in src:
        print("p4a patch already applied")
        return 0

    old_install = (
        '                "install -v --target \'{0}\' --no-deps'
        ' -r requirements.txt"'
    )
    new_install = (
        '                "install -v --target \'{0}\' --no-deps'
        ' --only-binary=:all: "\n'
        '                + _iva_pip_platform_args + " -r requirements.txt"'
    )
    if src.count(old_install) != 1:
        print(
            "p4a patch: install-line anchor not found (count=%d); "
            "p4a probably changed, aborting" % src.count(old_install),
            file=sys.stderr,
        )
        return 1
    src = src.replace(old_install, new_install)

    anchor2 = (
        "            shprint(sh.bash, '-c', (\n"
        '                "venv/bin/pip " +'
    )
    insert = (
        "            # " + MARKER + "\n"
        "            # process_python_modules() may resolve android-tagged wheels\n"
        "            # (e.g. charset_normalizer-...-android_24_arm64_v8a.whl); the\n"
        "            # host pip rejects them without explicit --platform tags, so\n"
        "            # pass the same tags the resolver used (per-arch).\n"
        "            _iva_pip_platform_args = \" \".join(\n"
        '                "--platform=" + tag for tag in\n'
        "                PyProjectRecipe.get_wheel_platform_tags(arch.arch, ctx)\n"
        "            )\n"
    )
    if src.count(anchor2) != 1:
        print(
            "p4a patch: shprint anchor not found (count=%d); "
            "p4a probably changed, aborting" % src.count(anchor2),
            file=sys.stderr,
        )
        return 1
    src = src.replace(anchor2, insert + anchor2)

    open(P4A_BUILD_PY, "w").write(src)
    print("p4a patch applied: android wheels accepted in pymodules install")
    return 0


if __name__ == "__main__":
    sys.exit(main())
