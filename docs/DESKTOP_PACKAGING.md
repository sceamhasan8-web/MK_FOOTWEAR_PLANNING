# Windows Desktop Application Packaging Guide

## 1. Overview
The Footwear Manufacturing ERP Windows Desktop client is built with **Kotlin 2.0** and **Compose Multiplatform (Desktop)**.
It compiles to standalone native Windows executables (`.exe`) and Windows Installer packages (`.msi`).

---

## 2. Prerequisites
1. **JDK 17 or 21** installed on the build machine (e.g., Eclipse Adoptium Temurin 21 or Amazon Corretto 21).
   - Ensure `JAVA_HOME` environment variable is set.
2. **WiX Toolset v3.11+** (required only if generating `.msi` installers).
   - Can be installed via `winget install WiX` or downloaded from github.com/wixtoolset/wix3.

---

## 3. Running Locally in Development Mode

Navigate to the `frontend-kotlin` directory:
```powershell
cd d:\ErpPlanning\frontend-kotlin
./gradlew :desktop:run
```
The desktop application will launch connected to `http://localhost:8000/api/v1` by default.

---

## 4. Packaging Native Windows Distribution

### A. Generate Standalone Native Application Folder (Portable `.exe`)
```powershell
./gradlew :desktop:packageReleaseUberJarForCurrentOS
# OR for native image package:
./gradlew :desktop:packageAppImage
```
The output will be generated at:
```text
frontend-kotlin/desktop/build/compose/binaries/main/app/FootwearManufacturingERP/
├── FootwearManufacturingERP.exe
└── runtime/
```
This folder contains the complete, self-contained desktop runtime and can be zipped and distributed to office desktop planning computers without requiring Java to be installed on client PCs.

### B. Generate Windows MSI Installer
```powershell
./gradlew :desktop:packageMsi
```
Output:
```text
frontend-kotlin/desktop/build/compose/binaries/main/msi/FootwearManufacturingERP-1.0.0.msi
```

### C. Generate Windows EXE Installer
```powershell
./gradlew :desktop:packageExe
```
Output:
```text
frontend-kotlin/desktop/build/compose/binaries/main/exe/FootwearManufacturingERP-1.0.0.exe
```

---

## 5. Client Configuration & Network Endpoint
To point the packaged Windows client to your central factory server:
1. In the login screen or configuration dialog, enter the central server URL (e.g. `http://192.168.1.100:8000/api/v1`).
2. Alternatively, define an environment variable on the Windows client machines:
   ```cmd
   setx ERP_API_BASE "http://192.168.1.100:8000/api/v1"
   ```
