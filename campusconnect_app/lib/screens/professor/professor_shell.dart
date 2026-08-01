import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';
import '../shared/account_sheet.dart';
import '../shared/active_sessions_screen.dart';
import '../shared/announcements_screen.dart';
import '../shared/generate_qr_screen.dart';

class ProfessorShell extends StatefulWidget {
  const ProfessorShell({super.key});

  @override
  State<ProfessorShell> createState() => _ProfessorShellState();
}

class _ProfessorShellState extends State<ProfessorShell> {
  int _index = 0;

  static const _titles = ['Dashboard', 'Generate QR', 'Live attendance', 'Announcements'];

  @override
  Widget build(BuildContext context) {
    final pages = [
      _ProfessorHome(onGo: (i) => setState(() => _index = i)),
      const GenerateQrScreen(showAppBar: false),
      const ActiveSessionsScreen(showAppBar: false),
      const AnnouncementsScreen(showAppBar: false),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: const [AccountButton()],
      ),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.qr_code_2), label: 'QR'),
          NavigationDestination(icon: Icon(Icons.groups_outlined), label: 'Live'),
          NavigationDestination(icon: Icon(Icons.campaign_outlined), label: 'News'),
        ],
      ),
    );
  }
}

class _ProfessorHome extends StatefulWidget {
  const _ProfessorHome({required this.onGo});

  final void Function(int tabIndex) onGo;

  @override
  State<_ProfessorHome> createState() => _ProfessorHomeState();
}

class _ProfessorHomeState extends State<_ProfessorHome> {
  late Future<_ProfessorData> _future = _load();

  Future<_ProfessorData> _load() async {
    final results = await Future.wait([
      appState.api.schedules(),
      appState.api.attendanceSessions(),
      appState.api.attendanceLog(),
    ]);

    return _ProfessorData(
      schedules: results[0] as List<ClassSchedule>,
      sessions: results[1] as List<AttendanceSession>,
      attendance: results[2] as List<AttendanceRecord>,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final user = appState.user!;

    return FutureBuilder<_ProfessorData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return StatusView(
            icon: Icons.cloud_off,
            title: 'Could not load your dashboard',
            message: snapshot.error.toString(),
            onRetry: () => setState(() => _future = _load()),
          );
        }

        final data = snapshot.data!;

        return RefreshIndicator(
          onRefresh: () async => setState(() => _future = _load()),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Welcome,',
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(color: theme.hintColor),
                      ),
                      Text(
                        user.fullname,
                        style: theme.textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      Text(
                        'Employee ID ${user.userId}',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.hintColor),
                      ),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: () => widget.onGo(1),
                        icon: const Icon(Icons.qr_code_2),
                        label: const Text('Generate attendance QR'),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: StatTile(
                      label: 'My classes',
                      value: data.schedules.length.toString(),
                      icon: Icons.menu_book_outlined,
                      color: kBrandBlue,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatTile(
                      label: 'Open sessions',
                      value: data.sessions.length.toString(),
                      icon: Icons.bolt_outlined,
                      color: kBrandAmber,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatTile(
                      label: 'Records',
                      value: data.attendance.length.toString(),
                      icon: Icons.fact_check_outlined,
                      color: kBrandMint,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'My class schedule',
                subtitle: data.schedules.isEmpty
                    ? 'No classes are assigned to your name yet.'
                    : null,
                children: [
                  for (final schedule in data.schedules)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Container(
                        padding: const EdgeInsets.all(9),
                        decoration: BoxDecoration(
                          color: kBrandBlue.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.menu_book_outlined,
                            size: 20, color: kBrandBlue),
                      ),
                      title: Text('${schedule.subjectCode} — ${schedule.subjectName}'),
                      subtitle: Text(
                        '${schedule.day} · ${schedule.time}'
                        '${schedule.room.isEmpty ? '' : ' · ${schedule.room}'}',
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Latest attendance',
                trailing: TextButton(
                  onPressed: () => widget.onGo(2),
                  child: const Text('Live'),
                ),
                children: [
                  if (data.attendance.isEmpty)
                    Text(
                      'No students have scanned in yet.',
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.hintColor),
                    )
                  else
                    for (final record in data.attendance.take(6))
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: CircleAvatar(
                          radius: 16,
                          backgroundColor: kBrandMint.withValues(alpha: 0.18),
                          child: const Icon(Icons.check, size: 16, color: kBrandMint),
                        ),
                        title: Text(record.fullname),
                        subtitle: Text(
                          '${record.subjectCode} · ${record.date} ${record.time}',
                        ),
                      ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ProfessorData {
  const _ProfessorData({
    required this.schedules,
    required this.sessions,
    required this.attendance,
  });

  final List<ClassSchedule> schedules;
  final List<AttendanceSession> sessions;
  final List<AttendanceRecord> attendance;
}
