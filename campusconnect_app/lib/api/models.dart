// Plain data classes mirroring the JSON the Flask API (api.py) returns.

String _s(dynamic v) => v == null ? '' : v.toString();

int _i(dynamic v) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(_s(v)) ?? 0;
}

enum UserRole { student, professor, admin }

UserRole roleFromString(String value) {
  switch (value.toLowerCase()) {
    case 'admin':
      return UserRole.admin;
    case 'professor':
      return UserRole.professor;
    default:
      return UserRole.student;
  }
}

String roleToString(UserRole role) => role.name;

String roleLabel(UserRole role) {
  switch (role) {
    case UserRole.student:
      return 'Student';
    case UserRole.professor:
      return 'Professor';
    case UserRole.admin:
      return 'Administrator';
  }
}

class AppUser {
  const AppUser({required this.role, required this.userId, required this.fullname});

  final UserRole role;
  final String userId;
  final String fullname;

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        role: roleFromString(_s(json['role'])),
        userId: _s(json['user_id']),
        fullname: _s(json['fullname']),
      );

  Map<String, dynamic> toJson() => {
        'role': roleToString(role),
        'user_id': userId,
        'fullname': fullname,
      };

  /// "Vincent Seco" -> "VS"
  String get initials {
    final parts = fullname.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }
}

class Announcement {
  const Announcement({
    required this.id,
    required this.title,
    required this.description,
    required this.dateCreated,
  });

  final int id;
  final String title;
  final String description;
  final String dateCreated;

  factory Announcement.fromJson(Map<String, dynamic> json) => Announcement(
        id: _i(json['id']),
        title: _s(json['title']),
        description: _s(json['description']),
        dateCreated: _s(json['date_created']),
      );
}

class Subject {
  const Subject({
    required this.id,
    required this.subjectCode,
    required this.subjectName,
    required this.professor,
    required this.yearLevel,
    required this.semester,
  });

  final int id;
  final String subjectCode;
  final String subjectName;
  final String professor;
  final String yearLevel;
  final String semester;

  factory Subject.fromJson(Map<String, dynamic> json) => Subject(
        id: _i(json['id']),
        subjectCode: _s(json['subject_code']),
        subjectName: _s(json['subject_name']),
        professor: _s(json['professor']),
        yearLevel: _s(json['year_level']),
        semester: _s(json['semester']),
      );
}

class ClassSchedule {
  const ClassSchedule({
    required this.id,
    required this.subjectCode,
    required this.subjectName,
    required this.professor,
    required this.professorId,
    required this.day,
    required this.time,
    required this.room,
    required this.classType,
  });

  final int id;
  final String subjectCode;
  final String subjectName;
  final String professor;
  final String professorId;
  final String day;
  final String time;
  final String room;
  final String classType;

  factory ClassSchedule.fromJson(Map<String, dynamic> json) => ClassSchedule(
        id: _i(json['id']),
        subjectCode: _s(json['subject_code']),
        subjectName: _s(json['subject_name']),
        professor: _s(json['professor']),
        professorId: _s(json['professor_id']),
        day: _s(json['day']),
        time: _s(json['time']),
        room: _s(json['room']),
        classType: _s(json['class_type']),
      );

  String get label => '$subjectCode — $subjectName';
}

class Professor {
  const Professor({
    required this.id,
    required this.employeeId,
    required this.fullname,
    required this.email,
    required this.department,
  });

  final int id;
  final String employeeId;
  final String fullname;
  final String email;
  final String department;

  factory Professor.fromJson(Map<String, dynamic> json) => Professor(
        id: _i(json['id']),
        employeeId: _s(json['employee_id']),
        fullname: _s(json['fullname']),
        email: _s(json['email']),
        department: _s(json['department']),
      );
}

class Student {
  const Student({
    required this.id,
    required this.studentId,
    required this.fullname,
    required this.email,
  });

  final int id;
  final String studentId;
  final String fullname;
  final String email;

  factory Student.fromJson(Map<String, dynamic> json) => Student(
        id: _i(json['id']),
        studentId: _s(json['student_id']),
        fullname: _s(json['fullname']),
        email: _s(json['email']),
      );
}

class AttendanceRecord {
  const AttendanceRecord({
    required this.studentId,
    required this.fullname,
    required this.subjectCode,
    required this.subjectName,
    required this.professor,
    required this.date,
    required this.time,
    required this.status,
  });

  final String studentId;
  final String fullname;
  final String subjectCode;
  final String subjectName;
  final String professor;
  final String date;
  final String time;
  final String status;

  factory AttendanceRecord.fromJson(Map<String, dynamic> json) => AttendanceRecord(
        studentId: _s(json['student_id']),
        fullname: _s(json['fullname']),
        subjectCode: _s(json['subject_code']),
        subjectName: _s(json['subject_name']),
        professor: _s(json['professor']),
        date: _s(json['date']),
        time: _s(json['time']),
        status: _s(json['status']),
      );
}

class AttendanceSession {
  const AttendanceSession({
    required this.id,
    required this.token,
    required this.payload,
    required this.subjectCode,
    required this.subjectName,
    required this.professorId,
    required this.professorName,
    required this.day,
    required this.schedule,
    required this.date,
    required this.expiresAt,
    required this.active,
    required this.attendees,
  });

  final int id;
  final String token;
  final String payload;
  final String subjectCode;
  final String subjectName;
  final String professorId;
  final String professorName;
  final String day;
  final String schedule;
  final String date;
  final String expiresAt;
  final bool active;
  final List<AttendanceRecord> attendees;

  factory AttendanceSession.fromJson(Map<String, dynamic> json) => AttendanceSession(
        id: _i(json['id']),
        token: _s(json['token']),
        payload: _s(json['payload']),
        subjectCode: _s(json['subject_code']),
        subjectName: _s(json['subject_name']),
        professorId: _s(json['professor_id']),
        professorName: _s(json['professor_name']),
        day: _s(json['day']),
        schedule: _s(json['schedule']),
        date: _s(json['date']),
        expiresAt: _s(json['expires_at']),
        active: _i(json['active']) == 1,
        attendees: ((json['attendees'] as List?) ?? const [])
            .map((e) => AttendanceRecord.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
      );
}

class AdminStats {
  const AdminStats({
    required this.students,
    required this.professors,
    required this.subjects,
    required this.schedules,
    required this.announcements,
    required this.attendance,
    required this.activeSessions,
  });

  final int students;
  final int professors;
  final int subjects;
  final int schedules;
  final int announcements;
  final int attendance;
  final int activeSessions;

  factory AdminStats.fromJson(Map<String, dynamic> json) => AdminStats(
        students: _i(json['students']),
        professors: _i(json['professors']),
        subjects: _i(json['subjects']),
        schedules: _i(json['schedules']),
        announcements: _i(json['announcements']),
        attendance: _i(json['attendance']),
        activeSessions: _i(json['active_sessions']),
      );
}
