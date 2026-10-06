package ai.zereos.standalone
import android.app.Activity
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient

class MainActivity: Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val w=WebView(this)
        w.settings.javaScriptEnabled=true
        w.settings.domStorageEnabled=true
        w.settings.allowFileAccess=true
        w.settings.allowContentAccess=true
        w.webViewClient=WebViewClient()
        w.webChromeClient=WebChromeClient()
        w.loadUrl("file:///android_asset/index.html")
        setContentView(w)
    }
    override fun onBackPressed(){ val w=(window.decorView.findViewById<WebView>(android.R.id.content)); super.onBackPressed() }
}