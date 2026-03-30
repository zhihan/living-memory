import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not configured for $defaultTargetPlatform',
        );
    }
  }

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyARzrUX4Myy-DpI3i-Q2x2TcW9U0URhy3U',
    appId: '1:404986156809:ios:287844fc3147f4172965d8',
    messagingSenderId: '404986156809',
    projectId: 'living-memories-488001',
    storageBucket: 'living-memories-488001.firebasestorage.app',
    iosBundleId: 'net.cicmusic.meeting-assistant',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'YOUR_ANDROID_API_KEY',
    appId: 'YOUR_ANDROID_APP_ID',
    messagingSenderId: '404986156809',
    projectId: 'living-memories-488001',
  );
}
