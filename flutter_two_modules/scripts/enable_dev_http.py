"""Enable HTTP access to the local Django development server on Android.
Run AFTER flutter create . ; for demo/dev only, NOT production deployments.
"""
from pathlib import Path
p = Path(__file__).resolve().parent.parent / 'android/app/src/main/AndroidManifest.xml'
if not p.is_file():
    raise SystemExit('Cannot find AndroidManifest.xml; run flutter create . first')
s = p.read_text(encoding='utf-8')
if 'android.permission.INTERNET' not in s:
    s = s.replace('<application', '    <uses-permission android:name="android.permission.INTERNET" />\n    <application', 1)
if 'android:usesCleartextTraffic=' not in s:
    s = s.replace('<application', '<application android:usesCleartextTraffic="true"', 1)
p.write_text(s, encoding='utf-8')
print('Android HTTP dev mode enabled in', p)
