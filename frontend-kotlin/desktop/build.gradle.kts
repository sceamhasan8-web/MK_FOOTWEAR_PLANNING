plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
}

kotlin {
    jvm {
        withJava()
    }

    sourceSets {
        val jvmMain by getting {
            dependencies {
                implementation(project(":shared"))
                implementation(compose.desktop.currentOs)
                implementation(libs.kotlinx.coroutines.swing)
            }
        }
    }
}

compose.desktop {
    application {
        mainClass = "com.footwear.erp.desktop.MainKt"

        nativeDistributions {
            targetFormats(org.jetbrains.compose.desktop.application.dsl.TargetFormat.Msi, org.jetbrains.compose.desktop.application.dsl.TargetFormat.Exe)
            packageName = "FootwearManufacturingERP"
            packageVersion = "1.0.0"
            description = "Footwear Manufacturing Production Planning ERP Desktop Client"
            vendor = "Footwear Manufacturing ERP"
            windows {
                menuGroup = "Footwear ERP"
                upgradeUuid = "6C10B0E5-3A87-4B21-82EE-5F11F1D8A291"
            }
        }
    }
}
