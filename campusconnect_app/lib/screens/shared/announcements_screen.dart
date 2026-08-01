import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../widgets/common.dart';

/// Announcement feed. Admins additionally get post / edit / delete.
class AnnouncementsScreen extends StatefulWidget {
  const AnnouncementsScreen({super.key, this.canManage = false, this.showAppBar = true});

  final bool canManage;
  final bool showAppBar;

  @override
  State<AnnouncementsScreen> createState() => _AnnouncementsScreenState();
}

class _AnnouncementsScreenState extends State<AnnouncementsScreen> {
  VoidCallback? _refresh;

  Future<void> _openEditor({Announcement? existing}) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _AnnouncementEditor(existing: existing),
    );

    if (saved == true) _refresh?.call();
  }

  Future<void> _delete(Announcement announcement) async {
    final ok = await confirm(
      context,
      title: 'Delete announcement',
      message: 'Delete "${announcement.title}"? Students will no longer see it.',
    );
    if (!ok) return;

    try {
      await appState.api.deleteAnnouncement(announcement.id);
      if (mounted) showSuccess(context, 'Announcement deleted.');
      _refresh?.call();
    } catch (error) {
      if (mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final body = AsyncList<Announcement>(
      load: appState.api.announcements,
      controllerHook: (refresh) => _refresh = refresh,
      emptyIcon: Icons.campaign_outlined,
      emptyTitle: 'No announcements yet',
      emptyMessage: widget.canManage
          ? 'Tap the + button to post the first announcement.'
          : 'New posts from the administration will show up here.',
      itemBuilder: (context, announcement, refresh) => _AnnouncementCard(
        announcement: announcement,
        canManage: widget.canManage,
        onEdit: () => _openEditor(existing: announcement),
        onDelete: () => _delete(announcement),
      ),
    );

    if (!widget.showAppBar) return body;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Announcements'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: () => _refresh?.call(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      floatingActionButton: widget.canManage
          ? FloatingActionButton.extended(
              onPressed: () => _openEditor(),
              icon: const Icon(Icons.add),
              label: const Text('Post'),
            )
          : null,
      body: body,
    );
  }
}

class _AnnouncementCard extends StatelessWidget {
  const _AnnouncementCard({
    required this.announcement,
    required this.canManage,
    required this.onEdit,
    required this.onDelete,
  });

  final Announcement announcement;
  final bool canManage;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

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
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(9),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(Icons.campaign_outlined,
                      size: 20, color: theme.colorScheme.primary),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    announcement.title,
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                if (canManage)
                  PopupMenuButton<String>(
                    onSelected: (value) => value == 'edit' ? onEdit() : onDelete(),
                    itemBuilder: (_) => const [
                      PopupMenuItem(value: 'edit', child: Text('Edit')),
                      PopupMenuItem(value: 'delete', child: Text('Delete')),
                    ],
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(announcement.description, style: theme.textTheme.bodyMedium),
            if (announcement.dateCreated.isNotEmpty) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.schedule, size: 14, color: theme.hintColor),
                  const SizedBox(width: 6),
                  Text(
                    announcement.dateCreated,
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _AnnouncementEditor extends StatefulWidget {
  const _AnnouncementEditor({this.existing});

  final Announcement? existing;

  @override
  State<_AnnouncementEditor> createState() => _AnnouncementEditorState();
}

class _AnnouncementEditorState extends State<_AnnouncementEditor> {
  final _formKey = GlobalKey<FormState>();
  late final _title = TextEditingController(text: widget.existing?.title ?? '');
  late final _description =
      TextEditingController(text: widget.existing?.description ?? '');

  bool _busy = false;

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _busy = true);
    try {
      if (widget.existing == null) {
        await appState.api.createAnnouncement(
          title: _title.text.trim(),
          description: _description.text.trim(),
        );
      } else {
        await appState.api.updateAnnouncement(
          id: widget.existing!.id,
          title: _title.text.trim(),
          description: _description.text.trim(),
        );
      }

      if (!mounted) return;
      Navigator.pop(context, true);
      showSuccess(context, 'Announcement saved.');
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
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.existing == null ? 'New announcement' : 'Edit announcement',
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _title,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(labelText: 'Title'),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Required.' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _description,
              minLines: 4,
              maxLines: 8,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Message',
                alignLabelWithHint: true,
              ),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Required.' : null,
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
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
