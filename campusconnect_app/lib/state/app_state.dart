import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../api/models.dart';

/// Holds the server address and the signed-in user, and persists both so the
/// app comes back logged in after a restart.
class AppState extends ChangeNotifier {
  AppState({ApiClient? client}) : api = client ?? ApiClient();

  static const _kBaseUrl = 'base_url';
  static const _kToken = 'token';
  static const _kUser = 'user';

  final ApiClient api;

  bool _ready = false;
  AppUser? _user;

  bool get ready => _ready;
  AppUser? get user => _user;
  bool get isLoggedIn => _user != null && (api.token?.isNotEmpty ?? false);
  String get baseUrl => api.baseUrl;
  bool get hasServer => api.baseUrl.isNotEmpty;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();

    api.baseUrl = prefs.getString(_kBaseUrl) ?? '';
    api.token = prefs.getString(_kToken);

    final rawUser = prefs.getString(_kUser);
    if (rawUser != null) {
      try {
        _user = AppUser.fromJson(Map<String, dynamic>.from(jsonDecode(rawUser) as Map));
      } catch (_) {
        _user = null;
      }
    }

    // A token that the server has forgotten (restart, logout elsewhere) must
    // not leave the app stuck on a dashboard that cannot load anything.
    if (_user != null && api.token != null && api.baseUrl.isNotEmpty) {
      try {
        _user = await api.me();
        await _persistUser();
      } on ApiException catch (error) {
        if (error.statusCode == 401 || error.statusCode == 403) {
          await _clearSession();
        }
      }
    }

    _ready = true;
    notifyListeners();
  }

  Future<void> setServer(String address) async {
    api.baseUrl = address;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kBaseUrl, api.baseUrl);
    notifyListeners();
  }

  Future<void> signIn({
    required UserRole role,
    required String identifier,
    required String password,
  }) async {
    final result = await api.login(role: role, identifier: identifier, password: password);
    api.token = result.token;
    _user = result.user;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, result.token);
    await _persistUser();

    notifyListeners();
  }

  Future<void> registerStudent({
    required String studentId,
    required String fullname,
    required String email,
    required String password,
  }) async {
    final result = await api.register(
      studentId: studentId,
      fullname: fullname,
      email: email,
      password: password,
    );
    api.token = result.token;
    _user = result.user;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, result.token);
    await _persistUser();

    notifyListeners();
  }

  Future<void> signOut() async {
    try {
      await api.logout();
    } catch (_) {
      // Dropping the local session matters more than telling the server.
    }
    await _clearSession();
    notifyListeners();
  }

  Future<void> _persistUser() async {
    final prefs = await SharedPreferences.getInstance();
    if (_user == null) {
      await prefs.remove(_kUser);
    } else {
      await prefs.setString(_kUser, jsonEncode(_user!.toJson()));
    }
  }

  Future<void> _clearSession() async {
    api.token = null;
    _user = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken);
    await prefs.remove(_kUser);
  }
}

/// Single instance shared by the whole app.
final appState = AppState();
