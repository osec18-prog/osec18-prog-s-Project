import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

/// Admin CRUD area: subjects, schedules, and read-only people directories.
class AdminManageScreen extends StatelessWidget {
  const AdminManageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 4,
      child: Column(
        children: [
          TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: [
              Tab(text: 'Subjects'),
              Tab(text: 'Schedules'),
              Tab(text: 'Students'),
              Tab(text: 'Professors'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _SubjectsTab(),
                _SchedulesTab(),
                _StudentsTab(),
                _ProfessorsTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------- subjects

class _SubjectsTab extends StatefulWidget {
  const _SubjectsTab();

  @override
  State<_SubjectsTab> createState() => _SubjectsTabState();
}

class _SubjectsTabState extends State<_SubjectsTab> {
  VoidCallback? _refresh;

  Future<void> _add() async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _SubjectEditor(),
    );
    if (saved == true) _refresh?.call();
  }

  Future<void> _delete(Subject subject) async {
    final ok = await confirm(
      context,
      title: 'Delete subject',
      message: 'Delete ${subject.subjectCode}? Existing schedules are not removed.',
    );
    if (!ok) return;

    try {
      await appState.api.deleteSubject(subject.id);
      if (mounted) showSuccess(context, 'Subject deleted.');
      _refresh?.call();
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        AsyncList<Subject>(
          load: appState.api.subjects,
          controllerHook: (refresh) => _refresh = refresh,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          emptyIcon: Icons.library_books_outlined,
          emptyTitle: 'No subjects yet',
          emptyMessage: 'Add a subject, then give it a schedule so it can be used '
              'for attendance QR codes.',
          itemBuilder: (context, subject, _) => Card(
            child: ListTile(
              title: Text('${subject.subjectCode} — ${subject.subjectName}'),
              subtitle: Text(
                [subject.professor, subject.yearLevel, subject.semester]
                    .where((s) => s.isNotEmpty)
                    .join(' · '),
              ),
              trailing: IconButton(
                icon: Icon(Icons.delete_outline, color: Theme.of(context).colorScheme.error),
                onPressed: () => _delete(subject),
              ),
            ),
          ),
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            heroTag: 'add-subject',
            onPressed: _add,
            icon: const Icon(Icons.add),
            label: const Text('Subject'),
          ),
        ),
      ],
    );
  }
}

class _SubjectEditor extends StatefulWidget {
  const _SubjectEditor();

  @override
  State<_SubjectEditor> createState() => _SubjectEditorState();
}

class _SubjectEditorState extends State<_SubjectEditor> {
  final _formKey = GlobalKey<FormState>();
  final _code = TextEditingController();
  final _name = TextEditingController();
  final _yearLevel = TextEditingController();

  String? _professor;
  String _semester = '1st Semester';
  bool _busy = false;
  final Future<List<Professor>> _professors = appState.api.professors();

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _yearLevel.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _busy = true);
    try {
      await appState.api.createSubject(
        subjectCode: _code.text.trim(),
        subjectName: _name.text.trim(),
        professor: _professor ?? '',
        yearLevel: _yearLevel.text.trim(),
        semester: _semester,
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      showSuccess(context, 'Subject added.');
    } catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'New subject',
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _code,
                decoration: const InputDecoration(labelText: 'Subject code'),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Required.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _name,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Subject name'),
                validator: (v) => (v ?? '').trim().isEmpty ? 'Required.' : null,
              ),
              const SizedBox(height: 12),
              FutureBuilder<List<Professor>>(
                future: _professors,
                builder: (context, snapshot) {
                  final professors = snapshot.data ?? const <Professor>[];
                  return DropdownButtonFormField<String>(
                    initialValue: _professor,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Professor'),
                    items: [
                      for (final professor in professors)
                        DropdownMenuItem(
                          value: professor.fullname,
                          child: Text(professor.fullname, overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (value) => setState(() => _professor = value),
                  );
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _yearLevel,
                decoration: const InputDecoration(
                  labelText: 'Year level',
                  hintText: '4th Year',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _semester,
                decoration: const InputDecoration(labelText: 'Semester'),
                items: const [
                  DropdownMenuItem(value: '1st Semester', child: Text('1st Semester')),
                  DropdownMenuItem(value: '2nd Semester', child: Text('2nd Semester')),
                ],
                onChanged: (value) => setState(() => _semester = value ?? _semester),
              ),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: _busy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Add subject'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// --------------------------------------------------------------- schedules

class _SchedulesTab extends StatefulWidget {
  const _SchedulesTab();

  @override
  State<_SchedulesTab> createState() => _SchedulesTabState();
}

class _SchedulesTabState extends State<_SchedulesTab> {
  VoidCallback? _refresh;

  Future<void> _add() async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _ScheduleEditor(),
    );
    if (saved == true) _refresh?.call();
  }

  Future<void> _delete(ClassSchedule schedule) async {
    final ok = await confirm(
      context,
      title: 'Delete schedule',
      message: 'Delete ${schedule.subjectCode} on ${schedule.day}?',
    );
    if (!ok) return;

    try {
      await appState.api.deleteSchedule(schedule.id);
      if (mounted) showSuccess(context, 'Schedule deleted.');
      _refresh?.call();
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        AsyncList<ClassSchedule>(
          load: () => appState.api.schedules(all: true),
          controllerHook: (refresh) => _refresh = refresh,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          emptyIcon: Icons.event_note_outlined,
          emptyTitle: 'No schedules yet',
          emptyMessage: 'Attendance QR codes are generated from schedules, so add '
              'one for each class.',
          itemBuilder: (context, schedule, _) => Card(
            child: ListTile(
              title: Text('${schedule.subjectCode} — ${schedule.subjectName}'),
              subtitle: Text(
                '${schedule.day} · ${schedule.time}'
                '${schedule.room.isEmpty ? '' : ' · ${schedule.room}'}\n'
                '${schedule.professor}'
                '${schedule.professorId.isEmpty ? '  (no employee ID matched)' : ' (${schedule.professorId})'}',
              ),
              isThreeLine: true,
              trailing: IconButton(
                icon: Icon(Icons.delete_outline, color: Theme.of(context).colorScheme.error),
                onPressed: () => _delete(schedule),
              ),
            ),
          ),
        ),
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton.extended(
            heroTag: 'add-schedule',
            onPressed: _add,
            icon: const Icon(Icons.add),
            label: const Text('Schedule'),
          ),
        ),
      ],
    );
  }
}

class _ScheduleEditor extends StatefulWidget {
  const _ScheduleEditor();

  @override
  State<_ScheduleEditor> createState() => _ScheduleEditorState();
}

class _ScheduleEditorState extends State<_ScheduleEditor> {
  final _formKey = GlobalKey<FormState>();
  final _room = TextEditingController();

  late final Future<_EditorLookups> _lookups = _loadLookups();

  Subject? _subject;
  String? _professor;
  String _day = 'Monday';
  String _classType = 'Face-to-Face';
  TimeOfDay _start = const TimeOfDay(hour: 8, minute: 0);
  TimeOfDay _end = const TimeOfDay(hour: 10, minute: 0);
  bool _busy = false;

  Future<_EditorLookups> _loadLookups() async {
    final results = await Future.wait([
      appState.api.subjects(),
      appState.api.professors(),
    ]);
    return _EditorLookups(
      subjects: results[0] as List<Subject>,
      professors: results[1] as List<Professor>,
    );
  }

  @override
  void dispose() {
    _room.dispose();
    super.dispose();
  }

  String _fmt(TimeOfDay time) =>
      '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    if (_subject == null) {
      showError(context, 'Choose a subject.');
      return;
    }

    setState(() => _busy = true);
    try {
      await appState.api.createSchedule(
        subjectCode: _subject!.subjectCode,
        subjectName: _subject!.subjectName,
        professor: _professor ?? _subject!.professor,
        day: _day,
        startTime: _fmt(_start),
        endTime: _fmt(_end),
        room: _room.text.trim(),
        yearLevel: _subject!.yearLevel,
        semester: _subject!.semester,
        classType: _classType,
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      showSuccess(context, 'Schedule added — it can now be used for QR codes.');
    } catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: SingleChildScrollView(
        child: FutureBuilder<_EditorLookups>(
          future: _lookups,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              );
            }

            final data = snapshot.data!;

            return Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'New schedule',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<int>(
                    initialValue: _subject?.id,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Subject'),
                    items: [
                      for (final subject in data.subjects)
                        DropdownMenuItem(
                          value: subject.id,
                          child: Text(
                            '${subject.subjectCode} — ${subject.subjectName}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    validator: (value) => value == null ? 'Choose a subject.' : null,
                    onChanged: (id) => setState(() {
                      _subject = data.subjects.firstWhere((s) => s.id == id);
                      _professor ??= _subject!.professor.isEmpty ? null : _subject!.professor;
                    }),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: data.professors.any((p) => p.fullname == _professor)
                        ? _professor
                        : null,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Professor'),
                    items: [
                      for (final professor in data.professors)
                        DropdownMenuItem(
                          value: professor.fullname,
                          child: Text(
                            '${professor.fullname} (${professor.employeeId})',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    validator: (value) =>
                        (value == null || value.isEmpty) ? 'Choose a professor.' : null,
                    onChanged: (value) => setState(() => _professor = value),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _day,
                    decoration: const InputDecoration(labelText: 'Day'),
                    items: const [
                      DropdownMenuItem(value: 'Monday', child: Text('Monday')),
                      DropdownMenuItem(value: 'Tuesday', child: Text('Tuesday')),
                      DropdownMenuItem(value: 'Wednesday', child: Text('Wednesday')),
                      DropdownMenuItem(value: 'Thursday', child: Text('Thursday')),
                      DropdownMenuItem(value: 'Friday', child: Text('Friday')),
                      DropdownMenuItem(value: 'Saturday', child: Text('Saturday')),
                    ],
                    onChanged: (value) => setState(() => _day = value ?? _day),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _TimeField(
                          label: 'Start',
                          value: _fmt(_start),
                          onTap: () async {
                            final picked = await showTimePicker(
                              context: context,
                              initialTime: _start,
                            );
                            if (picked != null) setState(() => _start = picked);
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _TimeField(
                          label: 'End',
                          value: _fmt(_end),
                          onTap: () async {
                            final picked = await showTimePicker(
                              context: context,
                              initialTime: _end,
                            );
                            if (picked != null) setState(() => _end = picked);
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _room,
                    decoration: const InputDecoration(
                      labelText: 'Room',
                      hintText: 'Laboratory 2',
                    ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _classType,
                    decoration: const InputDecoration(labelText: 'Class type'),
                    items: const [
                      DropdownMenuItem(value: 'Face-to-Face', child: Text('Face-to-Face')),
                      DropdownMenuItem(value: 'Online', child: Text('Online')),
                      DropdownMenuItem(value: 'Hybrid', child: Text('Hybrid')),
                    ],
                    onChanged: (value) => setState(() => _classType = value ?? _classType),
                  ),
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: _busy ? null : _save,
                    child: _busy
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Add schedule'),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _EditorLookups {
  const _EditorLookups({required this.subjects, required this.professors});

  final List<Subject> subjects;
  final List<Professor> professors;
}

class _TimeField extends StatelessWidget {
  const _TimeField({required this.label, required this.value, required this.onTap});

  final String label;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: const Icon(Icons.schedule),
        ),
        child: Text(value),
      ),
    );
  }
}

// ------------------------------------------------------------------ people

class _StudentsTab extends StatelessWidget {
  const _StudentsTab();

  @override
  Widget build(BuildContext context) {
    return AsyncList<Student>(
      load: appState.api.students,
      emptyIcon: Icons.people_outline,
      emptyTitle: 'No students registered',
      itemBuilder: (context, student, _) => Card(
        child: ListTile(
          leading: CircleAvatar(
            backgroundColor: kBrandBlue.withValues(alpha: 0.14),
            child: const Icon(Icons.school_outlined, size: 18, color: kBrandBlue),
          ),
          title: Text(student.fullname),
          subtitle: Text('${student.studentId} · ${student.email}'),
        ),
      ),
    );
  }
}

class _ProfessorsTab extends StatelessWidget {
  const _ProfessorsTab();

  @override
  Widget build(BuildContext context) {
    return AsyncList<Professor>(
      load: appState.api.professors,
      emptyIcon: Icons.badge_outlined,
      emptyTitle: 'No professors registered',
      itemBuilder: (context, professor, _) => Card(
        child: ListTile(
          leading: CircleAvatar(
            backgroundColor: kBrandMint.withValues(alpha: 0.14),
            child: const Icon(Icons.badge_outlined, size: 18, color: kBrandMint),
          ),
          title: Text(professor.fullname),
          subtitle: Text(
            [professor.employeeId, professor.department, professor.email]
                .where((s) => s.isNotEmpty)
                .join(' · '),
          ),
        ),
      ),
    );
  }
}
