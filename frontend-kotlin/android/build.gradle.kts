plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
}

kotlin {
    androidTarget()

    sourceSets {
        val androidMain by getting {
            dependencies {
                implementation(project(":shared"))
                implementation(libs.ktor.client.okhttp)
            }
        }
    }
}

android {
    namespace = "com.footwear.erp.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.footwear.erp.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}
