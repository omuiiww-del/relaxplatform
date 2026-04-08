[app]
title = Relax Platform
package.name = relaxplatform
package.domain = org.relax
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy,requests
presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png
android.permissions = INTERNET
android.api = 31
android.minapi = 21
android.ndk = 23b
android.sdk = 30
android.entrypoint = org.kivy.android.PythonActivity
android.whitelist = True
android.gradle_dependencies = 'com.google.android.material:material:1.4.0'
android.add_src =

[buildozer]
log_level = 2
warn_on_root = 1
