import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

/// Pick a class schedule, open an attendance session and show the QR full size
/// so students can scan it off the screen. Used by professors and admins.
class GenerateQrScreen extends StatefulWidget {
  const GenerateQrScreen({super.key, this.showAppBar = true});

  final bool showAppBar;

  @override
  State<GenerateQrScreen> createState() => _GenerateQrScreenState();
}

class _GenerateQrScreenState extends State<GenerateQrScreen> {
  late Future<List<ClassSchedule>> _future = appState.api.schedules();

  ClassSchedule? _selected;
  DateTime _date = DateTime.now();
  TimeOfDay _expiresAt = const TimeOfDay(hour: 23, minute: 59);
  AttendanceSession? _session;
  bool _busy = false;

  String get _dateText =>
      '${_date.year.toString().padLeft(4, '0')}-'
      '${_date.month.toString().padLeft(2, '0')}-'
      '${_date.day.toString().padLeft(2, '0')}';

  String get _timeText =>
      '${_expiresAt.hour.toString().padLeft(2, '0')}:'
      '${_expiresAt.minute.toString().padLeft(2, '0')}';

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(context: context, initialTime: _expiresAt);
    if (picked != null) setState(() => _expiresAt = picked);
  }

  Future<void> _generate() async {
    if (_selected == null) {
      showError(context, 'Choose a subject first.');
      return;
    }

    setState(() => _busy = true);
    try {
      final session = await appState.api.createAttendanceQr(
        scheduleId: _selected!.id,
        date: _dateText,
        expiresAt: _timeText,
      );
      if (!mounted) return;
      setState(() => _session = session);
    } catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _close() async {
    final session = _session;
    if (session == null) return;

    final ok = await confirm(
      context,
      title: 'Close attendance',
      message: 'Students will no longer be able to scan this QR code.',
      confirmLabel: 'Close session',
    );
    if (!ok) return;

    try {
      await appState.api.closeAttendanceSession(session.id);
      if (!mounted) return;
      setState(() => _session = null);
      showSuccess(context, 'Attendance session closed.');
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final body = FutureBuilder<List<ClassSchedule>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return StatusView(
            icon: Icons.cloud_off,
            title: 'Could not load your classes',
            message: snapshot.error.toString(),
            onRetry: () => setState(() => _future = appState.api.schedules()),
          );
        }

        final schedules = snapshot.data ?? const <ClassSchedule>[];

        if (schedules.isEmpty) {
          return StatusView(
            icon: Icons.event_busy,
            title: 'No class schedules found',
            message: appState.user?.role == UserRole.professor
                ? 'None of the schedules are assigned to your name yet. Ask the '
                    'administrator to add your class under Schedules.'
                : 'A subject only appears here once it has a schedule. Add one '
                    'under Schedules first.',
            onRetry: () => setState(() => _future = appState.api.schedules()),
            retryLabel: 'Refresh',
          );
        }

        // Keep the dropdown selection valid after a refresh.
        if (_selected != null && !schedules.any((s) => s.id == _selected!.id)) {
          _selected = null;
        }

        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            SectionCard(
              title: 'Open an attendance session',
              subtitle: 'Students scan the generated code to be marked present.',
              children: [
                DropdownButtonFormField<int>(
                  initialValue: _selected?.id,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Subject'),
                  items: [
                    for (final schedule in schedules)
                      DropdownMenuItem(
                        value: schedule.id,
                        child: Text(
                          '${schedule.subjectCode} — ${schedule.subjectName}'
                          '  (${schedule.day} ${schedule.time})',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (id) => setState(() {
                    _selected = schedules.firstWhere((s) => s.id == id);
                  }),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _PickerField(
                        label: 'Date',
                        value: _dateText,
                        icon: Icons.calendar_today_outlined,
                        onTap: _pickDate,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _PickerField(
                        label: 'Expires at',
                        value: _timeText,
                        icon: Icons.timer_outlined,
                        onTap: _pickTime,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _busy ? null : _generate,
                  icon: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.qr_code_2),
                  label: Text(_busy ? 'Generating…' : 'Generate QR'),
                ),
              ],
            ),
            if (_session != null) ...[
              const SizedBox(height: 16),
              _QrCard(session: _session!, onClose: _close),
            ],
          ],
        );
      },
    );

    if (!widget.showAppBar) return body;

    return Scaffold(
      appBar: AppBar(title: const Text('Generate attendance QR')),
      body: body,
    );
  }
}

class _PickerField extends StatelessWidget {
  const _PickerField({
    required this.label,
    required this.value,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final String value;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: InputDecorator(
        decoration: InputDecoration(labelText: label, prefixIcon: Icon(icon)),
        child: Text(value),
      ),
    );
  }
}

class _QrCard extends StatelessWidget {
  const _QrCard({required this.session, required this.onClose});

  final AttendanceSession session;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
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
                const Pill(text: 'Active', color: kBrandMint, icon: Icons.bolt),
              ],
            ),
            const SizedBox(height: 18),
            // White backing so the code stays scannable in dark mode.
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
              ),
              child: QrImageView(
                data: session.payload,
                version: QrVersions.auto,
                size: 260,
                backgroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              '${session.day} · ${session.schedule}',
              style: theme.textTheme.bodyMedium,
            ),
            Text(
              'Valid on ${session.date} until ${session.expiresAt}',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: onClose,
              style: OutlinedButton.styleFrom(foregroundColor: kBrandRose),
              icon: const Icon(Icons.stop_circle_outlined),
              label: const Text('Close this session'),
            ),
          ],
        ),
      ),
    );
  }
}
