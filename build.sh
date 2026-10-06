#!/bin/zsh
# Build, sign and install PixProRefsel.app
#
# Signed with the Developer ID Application certificate, selected by SHA-1
# hash (an expired certificate can share the name). --timestamp keeps the
# signature valid after the certificate expires. A stable identity also
# keeps the Automation grant for Pixelmator Pro attached to the app.
set -e
cd "${0:A:h}"

SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"

if ! security find-identity -p codesigning | grep -q "$SIGN_ID"; then
    echo "error: signing identity $SIGN_ID not in keychain" >&2
    exit 1
fi

echo "==> killing any running instance"
pkill -x PixProRefsel 2>/dev/null || true
sleep 1

echo "==> building"
rm -rf build dist
# The help Flache and the Read Me button open: <App>-README.txt in Resources,
# made from README.md so there is one source.
/usr/bin/python3 "$HOME/My_Applications/_signing/pixpro_readme_txt.py" README.md PixProRefsel-README.txt
./venv/bin/python setup.py py2app >/dev/null

# macOS 26+ draws an app with only an .icns shrunk onto a plain plate; the
# Icon Composer document compiles into Assets.car, which it uses instead.
~/bin/glass_icon dist/PixProRefsel.app icon/AppIcon.icon

# Sign by what a file IS (Mach-O), not by its extension.
echo "==> signing nested binaries"
find dist/PixProRefsel.app -type f -print0 | while IFS= read -r -d $'\0' f; do
    if file -b "$f" 2>/dev/null | grep -q 'Mach-O'; then
        codesign --force --timestamp --options runtime --sign "$SIGN_ID" "$f" 2>/dev/null || true
    fi
done
find dist/PixProRefsel.app -name '*.framework' -print0 2>/dev/null \
    | xargs -0 -n1 -I{} codesign --force --timestamp --options runtime --sign "$SIGN_ID" {} 2>/dev/null || true

echo "==> signing the bundle"
codesign --force --timestamp --options runtime \
    --entitlements "$HOME/My_Applications/_signing/pixpro.entitlements" --sign "$SIGN_ID" dist/PixProRefsel.app
codesign --verify --strict dist/PixProRefsel.app

if [[ "$1" == "--no-install" ]]; then
    echo "==> --no-install: leaving /Applications alone"
    exit 0
fi

echo "==> installing to /Applications"
rm -rf /Applications/PixProRefsel.app
cp -R dist/PixProRefsel.app /Applications/
xattr -dr com.apple.quarantine /Applications/PixProRefsel.app 2>/dev/null || true
codesign -dv /Applications/PixProRefsel.app 2>&1 | grep -E "Identifier=|Authority=|Timestamp="
plutil -extract CFBundleShortVersionString raw /Applications/PixProRefsel.app/Contents/Info.plist
