import 'dart:async';

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

/// Live view of open attendance sessions and who has scanned in.
/// Polls every 10 seconds so the list fills in as students scan.
class ActiveSessionsScreen extends StatefulWidget {
  const ActiveSessionsScreen({super.key, this.showAppBar = true});

  final bool showAppBar;

  @override
  State<ActiveSessionsScreen> createState() => _ActiveSessionsScreenState();
}

class _ActiveSessionsScreenState extends State<ActiveSessionsScreen> {
  late Future<List<AttendanceSession>> _future = appState.api.attendanceSessions();
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _reload(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _reload({bool silent = false}) {
    if (!mounted) return;
    setState(() => _future = appState.api.attendanceSessions());
    if (!silent) showSuccess(context, 'Refreshed.');
  }

  Future<void> _close(AttendanceSession session) async {
    final ok = await confirm(
      context,
      title: 'Close attendance',
      message: 'Close the session for ${session.subjectCode}? '
          'Students will no longer be able to scan.',
      confirmLabel: 'Close session',
    );
    if (!ok) return;

    try {
      await appState.api.closeAttendanceSession(session.id);
      if (!mounted) return;
      showSuccess(context, 'Session closed.');
      _reload(silent: true);
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  void _showQr(AttendanceSession session) {
    showDialog<void>(
      context: context,
      builder: (context) => Dialog(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${session.subjectCode} — ${session.subjectName}',
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: QrImageView(
                  data: session.payload,
                  version: QrVersions.auto,
                  size: 240,
                  backgroundColor: Colors.white,
                ),
              ),
              const SizedBox(height: 12),
              Text('Expires ${session.date} ${session.expiresAt}'),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Close'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final body = FutureBuilder<List<AttendanceSession>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting &&
            !snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return StatusView(
            icon: Icons.cloud_off,
            title: 'Could not load sessions',
            message: snapshot.error.toString(),
            onRetry: _reload,
          );
        }

        final sessions = snapshot.data ?? const <AttendanceSession>[];

        if (sessions.isEmpty) {
          return RefreshIndicator(
            onRefresh: () async => _reload(silent: true),
            child: ListView(
              children: const [
                SizedBox(
                  height: 420,
                  child: StatusView(
                    icon: Icons.bolt_outlined,
                    title: 'No open attendance sessions',
                    message: 'Generate a QR code to start taking attendance.',
                  ),
                ),
              ],
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: () async => _reload(silent: true),
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            itemCount: sessions.length,
            separatorBuilder: (_, _) => const SizedBox(height: 14),
            itemBuilder: (context, index) => _SessionCard(
              session: sessions[index],
              onClose: () => _close(sessions[index]),
              onShowQr: () => _showQr(sessions[index]),
            ),
          ),
        );
      },
    );

    if (!widget.showAppBar) return body;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Active attendance'),
        actions: [
          IconButton(onPressed: _reload, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: body,
    );
  }
}

class _SessionCard extends StatelessWidget {
  const _SessionCard({
    required this.session,
    required this.onClose,
    required this.onShowQr,
  });

  final AttendanceSession session;
  final VoidCallback onClose;
  final VoidCallback onShowQr;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        session.subjectCode,
                        style: theme.textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      Text(session.subjectName, style: theme.textTheme.bodyMedium),
                    ],
                  ),
                ),
                Pill(
                  text: '${session.attendees.length} scanned',
                  color: kBrandBlue,
                  icon: Icons.groups_outlined,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '${session.day} · ${session.schedule}  ·  expires '
              '${session.date} ${session.expiresAt}',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
            const SizedBox(height: 14),
            if (session.attendees.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  'Waiting for the first scan…',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
                ),
              )
            else
              Column(
                children: [
                  for (final attendee in session.attendees)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: CircleAvatar(
                        radius: 16,
                        backgroundColor: kBrandMint.withValues(alpha: 0.18),
                        child: const Icon(Icons.check, size: 16, color: kBrandMint),
                      ),
                      title: Text(attendee.fullname),
                      subtitle: Text('${attendee.studentId} · ${attendee.time}'),
                    ),
                ],
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onShowQr,
                    icon: const Icon(Icons.qr_code_2),
                    label: const Text('Show QR'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onClose,
                    style: OutlinedButton.styleFrom(foregroundColor: kBrandRose),
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('Close'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
