/// Conditional import: picks the correct scan screen based on platform.
///
/// - On mobile (Android/iOS): uses the camera-based QR scanner with mobile_scanner
/// - On web: shows a placeholder message directing users to the mobile app
///
/// Both implementations export a class named `ScanScreen` with the same API
/// (a Widget), so the rest of the app uses this file and doesn't need to
/// know which platform it's running on.
export 'scan_screen_web.dart'
    if (dart.library.io) 'scan_screen_mobile.dart';

