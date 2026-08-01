import 'package:flutter/material.dart';

import '../api/api_client.dart';

/// Shows a red snack bar with the message from an [ApiException] (or anything).
void showError(BuildContext context, Object error) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(error is ApiException ? error.message : error.toString()),
      backgroundColor: Theme.of(context).colorScheme.error,
      duration: const Duration(seconds: 5),
    ),
  );
}

void showSuccess(BuildContext context, String message) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(message)),
  );
}

Future<bool> confirm(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Delete',
  bool destructive = true,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: destructive
              ? FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error)
              : null,
          onPressed: () => Navigator.pop(context, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}

/// Empty / error / loading placeholder used by every list screen.
class StatusView extends StatelessWidget {
  const StatusView({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.onRetry,
    this.retryLabel = 'Try again',
  });

  final IconData icon;
  final String title;
  final String? message;
  final VoidCallback? onRetry;
  final String retryLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 56, color: theme.colorScheme.primary.withValues(alpha: 0.7)),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            if (message != null) ...[
              const SizedBox(height: 8),
              Text(
                message!,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor),
              ),
            ],
            if (onRetry != null) ...[
              const SizedBox(height: 20),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(retryLabel),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A small labelled number tile for the dashboards.
class StatTile extends StatelessWidget {
  const StatTile({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(icon, color: color, size: 22),
            ),
            const SizedBox(height: 14),
            Text(
              value,
              style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
          ],
        ),
      ),
    );
  }
}

/// Card with a title row and free-form children, used all over the app.
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    this.title,
    this.subtitle,
    this.trailing,
    required this.children,
    this.padding = const EdgeInsets.all(18),
  });

  final String? title;
  final String? subtitle;
  final Widget? trailing;
  final List<Widget> children;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: padding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title != null)
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title!,
                          style: theme.textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        if (subtitle != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 2),
                            child: Text(
                              subtitle!,
                              style: theme.textTheme.bodySmall
                                  ?.copyWith(color: theme.hintColor),
                            ),
                          ),
                      ],
                    ),
                  ),
                  ?trailing,
                ],
              ),
            if (title != null && children.isNotEmpty) const SizedBox(height: 14),
            ...children,
          ],
        ),
      ),
    );
  }
}

/// Coloured pill for statuses like "Present" or "Active".
class Pill extends StatelessWidget {
  const Pill({super.key, required this.text, required this.color, this.icon});

  final String text;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13, color: color),
            const SizedBox(width: 5),
          ],
          Text(
            text,
            style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

/// Wraps a future-backed list: handles loading, errors, empty state and
/// pull-to-refresh in one place so the screens stay short.
class AsyncList<T> extends StatefulWidget {
  const AsyncList({
    super.key,
    required this.load,
    required this.itemBuilder,
    required this.emptyTitle,
    this.emptyMessage,
    this.emptyIcon = Icons.inbox_outlined,
    this.header,
    this.padding = const EdgeInsets.fromLTRB(16, 16, 16, 32),
    this.separator = const SizedBox(height: 12),
    this.controllerHook,
  });

  final Future<List<T>> Function() load;
  final Widget Function(BuildContext context, T item, VoidCallback refresh) itemBuilder;
  final String emptyTitle;
  final String? emptyMessage;
  final IconData emptyIcon;
  final Widget Function(BuildContext context, List<T> items, VoidCallback refresh)? header;
  final EdgeInsets padding;
  final Widget separator;

  /// Lets a parent trigger [refresh] (e.g. after adding an item).
  final void Function(VoidCallback refresh)? controllerHook;

  @override
  State<AsyncList<T>> createState() => _AsyncListState<T>();
}

class _AsyncListState<T> extends State<AsyncList<T>> {
  late Future<List<T>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.load();
    widget.controllerHook?.call(_refresh);
  }

  void _refresh() {
    if (!mounted) return;
    setState(() => _future = widget.load());
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<T>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return StatusView(
            icon: Icons.cloud_off,
            title: 'Could not load data',
            message: snapshot.error is ApiException
                ? (snapshot.error as ApiException).message
                : snapshot.error.toString(),
            onRetry: _refresh,
          );
        }

        final items = snapshot.data ?? const [];
        final header = widget.header?.call(context, items, _refresh);

        if (items.isEmpty) {
          return RefreshIndicator(
            onRefresh: () async => _refresh(),
            child: ListView(
              padding: widget.padding,
              children: [
                if (header != null) ...[header, const SizedBox(height: 8)],
                SizedBox(
                  height: 320,
                  child: StatusView(
                    icon: widget.emptyIcon,
                    title: widget.emptyTitle,
                    message: widget.emptyMessage,
                    onRetry: _refresh,
                    retryLabel: 'Refresh',
                  ),
                ),
              ],
            ),
          );
        }

        return RefreshIndicator(
          onRefresh: () async => _refresh(),
          child: ListView.separated(
            padding: widget.padding,
            itemCount: items.length + (header != null ? 1 : 0),
            separatorBuilder: (_, _) => widget.separator,
            itemBuilder: (context, index) {
              if (header != null && index == 0) return header;
              final item = items[index - (header != null ? 1 : 0)];
              return widget.itemBuilder(context, item, _refresh);
            },
          ),
        );
      },
    );
  }
}
