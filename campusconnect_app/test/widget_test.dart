import 'package:campusconnect_app/api/api_client.dart';
import 'package:campusconnect_app/api/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('server address normalisation', () {
    test('bare IP gets a scheme and the default port', () {
      expect(ApiClient(baseUrl: '192.168.1.5').baseUrl, 'http://192.168.1.5:5000');
    });

    test('explicit port is kept', () {
      expect(ApiClient(baseUrl: '192.168.1.5:8000').baseUrl, 'http://192.168.1.5:8000');
    });

    test('full URL is kept and trailing slashes trimmed', () {
      expect(
        ApiClient(baseUrl: 'http://campus.local:5000/').baseUrl,
        'http://campus.local:5000',
      );
    });

    test('empty stays empty so the setup screen still shows', () {
      expect(ApiClient(baseUrl: '   ').baseUrl, '');
    });
  });

  group('models', () {
    test('roles map from the API strings', () {
      expect(roleFromString('admin'), UserRole.admin);
      expect(roleFromString('professor'), UserRole.professor);
      expect(roleFromString('student'), UserRole.student);
      expect(roleFromString('anything else'), UserRole.student);
    });

    test('initials come from the first and last name', () {
      const user = AppUser(
        role: UserRole.student,
        userId: '230208',
        fullname: 'Vincent Seco',
      );
      expect(user.initials, 'VS');
    });

    test('attendance session parses its attendees', () {
      final session = AttendanceSession.fromJson({
        'id': 7,
        'token': 'abc',
        'payload': 'CS4115|SE2|T003|Roshell|Thursday|2-7|2026-07-30|11:59 PM|abc',
        'subject_code': 'CS4115',
        'subject_name': 'Software Engineering 2',
        'professor_id': 'T003',
        'professor_name': 'Roshell Salvador',
        'day': 'Thursday',
        'schedule': '2:00 PM - 7:00 PM',
        'date': '2026-07-30',
        'expires_at': '11:59 PM',
        'active': 1,
        'attendees': [
          {
            'student_id': '230208',
            'fullname': 'Vincent Seco',
            'time': '04:20 PM',
            'status': 'Present',
          },
        ],
      });

      expect(session.active, isTrue);
      expect(session.attendees, hasLength(1));
      expect(session.attendees.first.fullname, 'Vincent Seco');
    });

    test('missing fields decode to empty strings instead of throwing', () {
      final record = AttendanceRecord.fromJson({'subject_code': 'CS4115'});
      expect(record.subjectCode, 'CS4115');
      expect(record.professor, '');
      expect(record.status, '');
    });
  });
}
