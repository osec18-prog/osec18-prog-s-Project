import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import 'api/models.dart';
import 'screens/admin/admin_shell.dart';
import 'screens/login_screen.dart';
import 'screens/professor/professor_shell.dart';
import 'screens/server_setup_screen.dart';
import 'screens/student/student_shell.dart';
import 'state/app_state.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await appState.load();

  // ── Auto-detect the server URL when running on web ──────────────
  // When the Flutter app is served by the Flask backend at /app/,
  // the web app can figure out the server address from the browser URL.
  if (kIsWeb && !appState.hasServer) {
    final origin = _getWebOrigin();
    if (origin != null) {
      await appState.setServer(origin);
    }
  }

  runApp(const CampusConnectApp());
}

/// Gets the page origin on web without importing dart:html directly.
/// On mobile this returns null (but is never called since kIsWeb is false).
String? _getWebOrigin() {
  try {
    // ignore: undefined_prefixed_name
    final uri = Uri.base;
    if (uri.isScheme('http') || uri.isScheme('https')) {
      final origin = '${uri.scheme}://${uri.host}';
      // Only auto-detect if it's not localhost
      if (uri.host != 'localhost' && uri.host != '127.0.0.1') {
        // If a non-standard port is used, include it
        if (uri.hasPort && uri.port != 80 && uri.port != 443) {
          return '$origin:${uri.port}';
        }
        return origin;
      }
    }
  } catch (_) {}
  return null;
}

class CampusConnectApp extends StatelessWidget {
  const CampusConnectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CampusConnect+',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: const _Root(),
    );
  }
}

/// Decides which screen to show based on the saved server address + session.
class _Root extends StatelessWidget {
  const _Root();

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: appState,
      builder: (context, _) {
        if (!appState.ready) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }

        if (!appState.hasServer) {
          return const ServerSetupScreen();
        }

        if (!appState.isLoggedIn) {
          return const LoginScreen();
        }

        switch (appState.user!.role) {
          case UserRole.admin:
            return const AdminShell();
          case UserRole.professor:
            return const ProfessorShell();
          case UserRole.student:
            return const StudentShell();
        }
      },
    );
  }
}
