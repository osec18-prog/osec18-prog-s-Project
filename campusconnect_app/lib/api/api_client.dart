import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Thrown for any non-2xx response or transport failure, carrying a message
/// that is safe to show the user directly.
class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class LoginResult {
  const LoginResult({required this.token, required this.user});

  final String token;
  final AppUser user;
}

/// Thin wrapper over the Flask JSON API in api.py.
class ApiClient {
  ApiClient({String baseUrl = '', this.token, http.Client? httpClient})
      : _baseUrl = _normalise(baseUrl),
        _http = httpClient ?? http.Client();

  final http.Client _http;

  String _baseUrl;
  String? token;

  static const Duration _timeout = Duration(seconds: 12);

  String get baseUrl => _baseUrl;

  set baseUrl(String value) => _baseUrl = _normalise(value);

  /// Accepts "192.168.1.5", "192.168.1.5:5000" or a full URL.
  static String _normalise(String raw) {
    var value = raw.trim();
    if (value.isEmpty) return '';
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'http://$value';
    }
    if (!RegExp(r':\d+$').hasMatch(value) && Uri.tryParse(value)?.hasPort != true) {
      value = '$value:5000';
    }
    return value.replaceAll(RegExp(r'/+$'), '');
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    if (_baseUrl.isEmpty) {
      throw ApiException('No server address set yet.');
    }
    return Uri.parse('$_baseUrl$path').replace(queryParameters: query);
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (token != null && token!.isNotEmpty) 'Authorization': 'Bearer $token',
      };

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
  }) async {
    final uri = _uri(path, query);

    http.Response response;
    try {
      final request = http.Request(method, uri)..headers.addAll(_headers);
      if (body != null) request.body = jsonEncode(body);

      final streamed = await _http.send(request).timeout(_timeout);
      response = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw ApiException('The server took too long to answer. Is it still running?');
    } on SocketException {
      throw ApiException(
        'Cannot reach $_baseUrl.\n\nCheck that the Flask server is running and that this '
        'device is on the same Wi-Fi network.',
      );
    } catch (error) {
      throw ApiException('Network error: $error');
    }

    Map<String, dynamic> decoded;
    try {
      final parsed = jsonDecode(response.body);
      decoded = parsed is Map<String, dynamic> ? parsed : <String, dynamic>{};
    } catch (_) {
      throw ApiException(
        'The server replied with something that is not JSON (HTTP ${response.statusCode}). '
        'Double-check the address points at the CampusConnect+ server.',
        statusCode: response.statusCode,
      );
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }

    throw ApiException(
      (decoded['message'] as String?) ?? 'Request failed (HTTP ${response.statusCode}).',
      statusCode: response.statusCode,
    );
  }

  List<Map<String, dynamic>> _list(Map<String, dynamic> json, String key) =>
      ((json[key] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();

  // ------------------------------------------------------------------ session

  /// Verifies an address really is a CampusConnect+ server.
  Future<void> ping({String? candidateBaseUrl}) async {
    final previous = _baseUrl;
    if (candidateBaseUrl != null) _baseUrl = _normalise(candidateBaseUrl);
    try {
      final json = await _send('GET', '/api/ping');
      if (json['service'] != 'CampusConnect+') {
        throw ApiException('That address answered, but it is not a CampusConnect+ server.');
      }
    } finally {
      if (candidateBaseUrl != null) _baseUrl = previous;
    }
  }

  Future<LoginResult> login({
    required UserRole role,
    required String identifier,
    required String password,
  }) async {
    final json = await _send('POST', '/api/login', body: {
      'role': roleToString(role),
      'identifier': identifier,
      'password': password,
    });

    return LoginResult(
      token: json['token'] as String,
      user: AppUser.fromJson(Map<String, dynamic>.from(json['user'] as Map)),
    );
  }

  Future<LoginResult> register({
    required String studentId,
    required String fullname,
    required String email,
    required String password,
  }) async {
    final json = await _send('POST', '/api/register', body: {
      'student_id': studentId,
      'fullname': fullname,
      'email': email,
      'password': password,
    });

    return LoginResult(
      token: json['token'] as String,
      user: AppUser.fromJson(Map<String, dynamic>.from(json['user'] as Map)),
    );
  }

  Future<void> logout() => _send('POST', '/api/logout');

  Future<AppUser> me() async {
    final json = await _send('GET', '/api/me');
    return AppUser.fromJson(Map<String, dynamic>.from(json['user'] as Map));
  }

  // ------------------------------------------------------------ announcements

  Future<List<Announcement>> announcements() async {
    final json = await _send('GET', '/api/announcements');
    return _list(json, 'announcements').map(Announcement.fromJson).toList();
  }

  Future<void> createAnnouncement({required String title, required String description}) =>
      _send('POST', '/api/announcements', body: {'title': title, 'description': description});

  Future<void> updateAnnouncement({
    required int id,
    required String title,
    required String description,
  }) =>
      _send('PUT', '/api/announcements/$id', body: {'title': title, 'description': description});

  Future<void> deleteAnnouncement(int id) => _send('DELETE', '/api/announcements/$id');

  // ------------------------------------------------- subjects and schedules

  Future<List<Subject>> subjects() async {
    final json = await _send('GET', '/api/subjects');
    return _list(json, 'subjects').map(Subject.fromJson).toList();
  }

  Future<void> createSubject({
    required String subjectCode,
    required String subjectName,
    required String professor,
    required String yearLevel,
    required String semester,
  }) =>
      _send('POST', '/api/subjects', body: {
        'subject_code': subjectCode,
        'subject_name': subjectName,
        'professor': professor,
        'year_level': yearLevel,
        'semester': semester,
      });

  Future<void> deleteSubject(int id) => _send('DELETE', '/api/subjects/$id');

  /// Professors get only their own classes unless [all] is true.
  Future<List<ClassSchedule>> schedules({bool all = false}) async {
    final json = await _send('GET', '/api/schedules', query: all ? {'all': '1'} : null);
    return _list(json, 'schedules').map(ClassSchedule.fromJson).toList();
  }

  Future<void> createSchedule({
    required String subjectCode,
    required String subjectName,
    required String professor,
    required String day,
    required String startTime,
    required String endTime,
    required String room,
    required String yearLevel,
    required String semester,
    required String classType,
  }) =>
      _send('POST', '/api/schedules', body: {
        'subject_code': subjectCode,
        'subject_name': subjectName,
        'professor': professor,
        'day': day,
        'start_time': startTime,
        'end_time': endTime,
        'room': room,
        'year_level': yearLevel,
        'semester': semester,
        'class_type': classType,
      });

  Future<void> deleteSchedule(int id) => _send('DELETE', '/api/schedules/$id');

  // -------------------------------------------------------------- directories

  Future<List<Professor>> professors() async {
    final json = await _send('GET', '/api/professors');
    return _list(json, 'professors').map(Professor.fromJson).toList();
  }

  Future<List<Student>> students() async {
    final json = await _send('GET', '/api/students');
    return _list(json, 'students').map(Student.fromJson).toList();
  }

  Future<AdminStats> stats() async {
    final json = await _send('GET', '/api/stats');
    return AdminStats.fromJson(Map<String, dynamic>.from(json['stats'] as Map));
  }

  // --------------------------------------------------------------- attendance

  /// Opens an attendance session; [expiresAt] is 24h "HH:mm".
  Future<AttendanceSession> createAttendanceQr({
    required int scheduleId,
    required String date,
    required String expiresAt,
  }) async {
    final json = await _send('POST', '/api/qr/create', body: {
      'schedule_id': scheduleId,
      'date': date,
      'expires_at': expiresAt,
    });

    return AttendanceSession.fromJson(Map<String, dynamic>.from(json['session'] as Map));
  }

  Future<List<AttendanceSession>> attendanceSessions() async {
    final json = await _send('GET', '/api/attendance/sessions');
    return _list(json, 'sessions').map(AttendanceSession.fromJson).toList();
  }

  Future<void> closeAttendanceSession(int id) =>
      _send('POST', '/api/attendance/sessions/$id/close');

  /// Records attendance for the logged-in student. Returns the server message.
  Future<String> scanAttendance(String qrPayload) async {
    final json = await _send('POST', '/api/attendance/scan', body: {'qr': qrPayload});
    return (json['message'] as String?) ?? 'Attendance recorded.';
  }

  Future<List<AttendanceRecord>> myAttendance() async {
    final json = await _send('GET', '/api/attendance/mine');
    return _list(json, 'attendance').map(AttendanceRecord.fromJson).toList();
  }

  Future<List<AttendanceRecord>> attendanceLog() async {
    final json = await _send('GET', '/api/attendance');
    return _list(json, 'attendance').map(AttendanceRecord.fromJson).toList();
  }

  void close() => _http.close();
}
