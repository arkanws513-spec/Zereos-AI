plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android { namespace="ai.zereos.standalone"; compileSdk=35
    defaultConfig { applicationId="ai.zereos.standalone"; minSdk=26; targetSdk=35; versionCode=2; versionName="1.0.1" }
    buildTypes { release { isMinifyEnabled=false } }
    compileOptions { sourceCompatibility=JavaVersion.VERSION_17; targetCompatibility=JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget="17" }
}