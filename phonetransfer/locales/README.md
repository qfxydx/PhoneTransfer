# Interface catalogs

All six UTF-8 JSON catalogs have identical source keys. Chinese source text is
used as a stable key, preserving the existing code's intent. Use
`tr("…{p0}…", p0=value)` for messages and pass runtime values separately;
never translate paths, filenames, shell commands or ADB protocol tokens.
Preserve every placeholder name, conversion (`!r`) and format (`:.1f`).

`phonetransfer/i18n.py` owns language negotiation, QSettings persistence, fallback,
resource loading and Qt standard-button translation. It reads resources relative
to `__file__`, so source execution and PyInstaller's extracted package use the
same layout. `PhoneTransfer.spec` explicitly includes this directory. Qt's
bundled qtbase catalogs provide other Qt controls when available; macOS native
panels and external tools retain their own language.

Keep preset constants and APK error explanations as source keys; translate at
their presentation boundary. New UI/error text must have entries in every
catalog. Unsupported preferred languages fall back to English; Chinese regional
and script variants use zh-CN. Language settings apply after quitting and
reopening the app, keeping worker sentinels and messages consistent throughout
an active session. Do not call `initialize` during a running operation.

Run `python3 scripts/run_tests.py` from the repository root. It validates literal
keys, complete catalogs, exact placeholders, all selection choices, fallback,
persistence, restart behavior, Qt buttons, shortcuts and six-language offscreen
layouts with mocked devices. `python3 scripts/capture_i18n.py` regenerates the
mocked screenshot evidence. Never use tests or screenshot capture to access or
delete actual device files.
