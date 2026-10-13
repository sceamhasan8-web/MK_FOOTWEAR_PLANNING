# Android Application Build & APK Generation Guide

## 1. Overview
The Footwear Manufacturing ERP Android mobile application is built with **Kotlin 2.0** and **Jetpack Compose / Compose Multiplatform (Android)**.
It provides shop-floor supervisors with quick order barcode lookup, section operation selection, fast quantity entry buttons, component piece tracking, and live progress dashboards over factory Wi-Fi.

---

## 2. Prerequisites
1. **JDK 17** installed with `JAVA_HOME` configured.
2. **Android SDK Platform 35** and **Build-Tools 35.0.0** installed.
   - Set environment variable `ANDROID_HOME` pointing to your Android SDK directory (e.g., `C:\Users\<user>\AppData\Local\Android\Sdk` on Windows or `/usr/lib/android-sdk` on Linux).

---

## 3. Building Debug APK for Testing

Navigate to the `frontend-kotlin` project directory:
```bash
cd d:\ErpPlanning\frontend-kotlin
./gradlew :android:assembleDebug
```
Output location:
```text
frontend-kotlin/android/build/outputs/apk/debug/android-debug.apk
```

You can install this directly onto an Android device or tablet via ADB:
```bash
adb install -r frontend-kotlin/android/build/outputs/apk/debug/android-debug.apk
```

---

## 4. Building Release Signed APK for Factory Production

### A. Generate Keystore (One-Time Setup)
```bash
keytool -genkey -v -keystore footwear-erp-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias footwear_key
```

### B. Configure Signing in `frontend-kotlin/android/build.gradle.kts`
```kotlin
android {
    ...
    signingConfigs {
        create("release") {
            storeFile = file("footwear-erp-key.jks")
            storePassword = System.getenv("KEYSTORE_PASSWORD") ?: "secret"
            keyAlias = "footwear_key"
            keyPassword = System.getenv("KEY_PASSWORD") ?: "secret"
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}
```

### C. Build Release APK
```bash
./gradlew :android:assembleRelease
```
Output location:
```text
frontend-kotlin/android/build/outputs/apk/release/android-release.apk
```

---

## 5. Shop-Floor Terminal Deployment & Network Configuration

1. **Local Wi-Fi Network**: Ensure all factory Android terminals are connected to the factory Wi-Fi network that has routing access to the central backend server (e.g. `192.168.1.100:8000`).
2. **Server Address Entry**: On the initial login screen of the app, supervisors enter the central server IP (e.g. `192.168.1.100:8000`) and log in with their allocated credentials (`supervisor` / `supervisor123`).
3. **Kiosk / Lock-Task Mode**: For dedicated barcode scanning tablets mounted on production lines, Android Lock-Task / Kiosk mode can be enabled to keep the app always open.
