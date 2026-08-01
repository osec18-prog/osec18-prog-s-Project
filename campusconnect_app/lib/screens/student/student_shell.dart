import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';
import '../shared/account_sheet.dart';
import '../shared/announcements_screen.dart';
import 'scan_screen.dart';

class StudentShell extends StatefulWidget {
  const StudentShell({super.key});

  @override
  State<StudentShell> createState() => _StudentShellState();
}

class _StudentShellState extends State<StudentShell> {
  int _index = 0;

  // Bumping this key rebuilds the attendance tab after a successful scan.
  int _attendanceRevision = 0;

  static const _titles = ['Dashboard', 'Announcements', 'Schedule', 'Attendance'];

  Future<void> _openScanner() async {
    final recorded = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const ScanScreen()),
    );

    if (recorded == true && mounted) {
      setState(() {
        _attendanceRevision++;
        _index = 3;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      _StudentHome(onScan: _openScanner, onSeeAll: (i) => setState(() => _index = i)),
      const AnnouncementsScreen(showAppBar: false),
      const _StudentSchedule(),
      _StudentAttendance(key: ValueKey(_attendanceRevision)),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: const [AccountButton()],
      ),
      body: pages[_index],
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openScanner,
        icon: const Icon(Icons.qr_code_scanner),
        label: const Text('Scan QR'),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.campaign_outlined), label: 'News'),
          NavigationDestination(icon: Icon(Icons.calendar_month_outlined), label: 'Schedule'),
          NavigationDestination(icon: Icon(Icons.fact_check_outlined), label: 'Attendance'),
        ],
      ),
    );
  }
}

class _StudentHome extends StatefulWidget {
  const _StudentHome({required this.onScan, required this.onSeeAll});

  final VoidCallback onScan;
  final void Function(int tabIndex) onSeeAll;

  @override
  State<_StudentHome> createState() => _StudentHomeState();
}

class _StudentHomeState extends State<_StudentHome> {
  late Future<_HomeData> _future = _load();

  Future<_HomeData> _load() async {
    final results = await Future.wait([
      appState.api.announcements(),
      appState.api.myAttendance(),
      appState.api.schedules(),
    ]);

    return _HomeData(
      announcements: results[0] as List<Announcement>,
      attendance: results[1] as List<AttendanceRecord>,
      schedules: results[2] as List<ClassSchedule>,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final user = appState.user!;

    return FutureBuilder<_HomeData>(
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
        final today = _weekdayName(DateTime.now().weekday);
        final todayClasses = data.schedules
            .where((s) => s.day.toLowerCase() == today.toLowerCase())
            .toList();

        return RefreshIndicator(
          onRefresh: () async => setState(() => _future = _load()),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Welcome back,',
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(color: theme.hintColor),
                      ),
                      Text(
                        user.fullname,
                        style: theme.textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Student ID ${user.userId}',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.hintColor),
                      ),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: widget.onScan,
                        icon: const Icon(Icons.qr_code_scanner),
                        label: const Text('Scan attendance QR'),
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
                      label: 'Times present',
                      value: data.attendance
                          .where((a) => a.status.toLowerCase() == 'present')
                          .length
                          .toString(),
                      icon: Icons.check_circle_outline,
                      color: kBrandMint,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatTile(
                      label: 'Classes today',
                      value: todayClasses.length.toString(),
                      icon: Icons.today_outlined,
                      color: kBrandBlue,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Today · $today',
                subtitle: todayClasses.isEmpty ? 'No classes scheduled' : null,
                trailing: TextButton(
                  onPressed: () => widget.onSeeAll(2),
                  child: const Text('All'),
                ),
                children: [
                  for (final item in todayClasses)
                    _ScheduleRow(schedule: item, dense: true),
                ],
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Latest announcement',
                trailing: TextButton(
                  onPressed: () => widget.onSeeAll(1),
                  child: const Text('All'),
                ),
                children: [
                  if (data.announcements.isEmpty)
                    Text(
                      'Nothing posted yet.',
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.hintColor),
                    )
                  else ...[
                    Text(
                      data.announcements.first.title,
                      style: theme.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      data.announcements.first.description,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      data.announcements.first.dateCreated,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.hintColor),
                    ),
                  ],
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _HomeData {
  const _HomeData({
    required this.announcements,
    required this.attendance,
    required this.schedules,
  });

  final List<Announcement> announcements;
  final List<AttendanceRecord> attendance;
  final List<ClassSchedule> schedules;
}

class _StudentSchedule extends StatelessWidget {
  const _StudentSchedule();

  @override
  Widget build(BuildContext context) {
    return AsyncList<ClassSchedule>(
      load: appState.api.schedules,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      emptyIcon: Icons.calendar_month_outlined,
      emptyTitle: 'No class schedules yet',
      emptyMessage: 'Your administrator has not published any schedules.',
      itemBuilder: (context, schedule, _) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: _ScheduleRow(schedule: schedule),
        ),
      ),
    );
  }
}

class _ScheduleRow extends StatelessWidget {
  const _ScheduleRow({required this.schedule, this.dense = false});

  final ClassSchedule schedule;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: EdgeInsets.symmetric(vertical: dense ? 6 : 0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              color: kBrandBlue.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.menu_book_outlined, size: 20, color: kBrandBlue),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  schedule.subjectCode,
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                Text(schedule.subjectName, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 12,
                  runSpacing: 2,
                  children: [
                    _MetaText(icon: Icons.schedule, text: '${schedule.day} · ${schedule.time}'),
                    if (schedule.room.isNotEmpty)
                      _MetaText(icon: Icons.meeting_room_outlined, text: schedule.room),
                    if (schedule.professor.isNotEmpty)
                      _MetaText(icon: Icons.person_outline, text: schedule.professor),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetaText extends StatelessWidget {
  const _MetaText({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: theme.hintColor),
        const SizedBox(width: 4),
        Text(text, style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
      ],
    );
  }
}

class _StudentAttendance extends StatelessWidget {
  const _StudentAttendance({super.key});

  @override
  Widget build(BuildContext context) {
    return AsyncList<AttendanceRecord>(
      load: appState.api.myAttendance,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      emptyIcon: Icons.fact_check_outlined,
      emptyTitle: 'No attendance records yet',
      emptyMessage: 'Scan the QR code your professor shows in class.',
      itemBuilder: (context, record, _) {
        final theme = Theme.of(context);
        final present = record.status.toLowerCase() == 'present';

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        record.subjectCode,
                        style: theme.textTheme.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      Text(record.subjectName, style: theme.textTheme.bodyMedium),
                      const SizedBox(height: 6),
                      _MetaText(
                        icon: Icons.event_available,
                        text: '${record.date} · ${record.time}',
                      ),
                      if (record.professor.isNotEmpty)
                        _MetaText(icon: Icons.person_outline, text: record.professor),
                    ],
                  ),
                ),
                Pill(
                  text: record.status.isEmpty ? 'Recorded' : record.status,
                  color: present ? kBrandMint : kBrandAmber,
                  icon: present ? Icons.check : Icons.info_outline,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

String _weekdayName(int weekday) {
  const names = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];
  return names[(weekday - 1).clamp(0, 6)];
}
