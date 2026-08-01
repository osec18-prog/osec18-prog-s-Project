import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';
import '../shared/account_sheet.dart';
import '../shared/active_sessions_screen.dart';
import '../shared/announcements_screen.dart';
import '../shared/generate_qr_screen.dart';
import 'admin_manage_screen.dart';

class AdminShell extends StatefulWidget {
  const AdminShell({super.key});

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  int _index = 0;

  static const _titles = [
    'Admin dashboard',
    'Announcements',
    'Manage',
    'Generate QR',
    'Live attendance',
  ];

  @override
  Widget build(BuildContext context) {
    final pages = [
      _AdminHome(onGo: (i) => setState(() => _index = i)),
      const AnnouncementsScreen(showAppBar: false, canManage: true),
      const AdminManageScreen(),
      const GenerateQrScreen(showAppBar: false),
      const ActiveSessionsScreen(showAppBar: false),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          if (_index == 1)
            IconButton(
              tooltip: 'New announcement',
              onPressed: () => setState(() => _index = 1),
              icon: const Icon(Icons.campaign_outlined),
            ),
          const AccountButton(),
        ],
      ),
      body: pages[_index],
      floatingActionButton: _index == 1
          ? null // the announcements screen brings its own action
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.campaign_outlined), label: 'News'),
          NavigationDestination(icon: Icon(Icons.tune), label: 'Manage'),
          NavigationDestination(icon: Icon(Icons.qr_code_2), label: 'QR'),
          NavigationDestination(icon: Icon(Icons.groups_outlined), label: 'Live'),
        ],
      ),
    );
  }
}

class _AdminHome extends StatefulWidget {
  const _AdminHome({required this.onGo});

  final void Function(int tabIndex) onGo;

  @override
  State<_AdminHome> createState() => _AdminHomeState();
}

class _AdminHomeState extends State<_AdminHome> {
  late Future<_AdminData> _future = _load();

  Future<_AdminData> _load() async {
    final results = await Future.wait([
      appState.api.stats(),
      appState.api.attendanceLog(),
    ]);
    return _AdminData(
      stats: results[0] as AdminStats,
      attendance: results[1] as List<AttendanceRecord>,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return FutureBuilder<_AdminData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return StatusView(
            icon: Icons.cloud_off,
            title: 'Could not load the dashboard',
            message: snapshot.error.toString(),
            onRetry: () => setState(() => _future = _load()),
          );
        }

        final data = snapshot.data!;
        final stats = data.stats;

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
                        'Signed in as',
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(color: theme.hintColor),
                      ),
                      Text(
                        appState.user!.fullname,
                        style: theme.textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: () => widget.onGo(3),
                              icon: const Icon(Icons.qr_code_2),
                              label: const Text('QR'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () => widget.onGo(1),
                              icon: const Icon(Icons.campaign_outlined),
                              label: const Text('Post'),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 14),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.35,
                children: [
                  StatTile(
                    label: 'Students',
                    value: stats.students.toString(),
                    icon: Icons.school_outlined,
                    color: kBrandBlue,
                  ),
                  StatTile(
                    label: 'Professors',
                    value: stats.professors.toString(),
                    icon: Icons.badge_outlined,
                    color: kBrandMint,
                  ),
                  StatTile(
                    label: 'Subjects',
                    value: stats.subjects.toString(),
                    icon: Icons.library_books_outlined,
                    color: kBrandAmber,
                  ),
                  StatTile(
                    label: 'Schedules',
                    value: stats.schedules.toString(),
                    icon: Icons.event_note_outlined,
                    color: kBrandDeep,
                  ),
                  StatTile(
                    label: 'Announcements',
                    value: stats.announcements.toString(),
                    icon: Icons.campaign_outlined,
                    color: kBrandRose,
                  ),
                  StatTile(
                    label: 'Open sessions',
                    value: stats.activeSessions.toString(),
                    icon: Icons.bolt_outlined,
                    color: kBrandBlue,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              SectionCard(
                title: 'Recent attendance',
                subtitle: '${stats.attendance} records in total',
                trailing: TextButton(
                  onPressed: () => widget.onGo(4),
                  child: const Text('Live'),
                ),
                children: [
                  if (data.attendance.isEmpty)
                    Text(
                      'No attendance has been recorded yet.',
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: theme.hintColor),
                    )
                  else
                    for (final record in data.attendance.take(8))
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
                        trailing: Text(
                          record.status,
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.hintColor),
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

class _AdminData {
  const _AdminData({required this.stats, required this.attendance});

  final AdminStats stats;
  final List<AttendanceRecord> attendance;
}
