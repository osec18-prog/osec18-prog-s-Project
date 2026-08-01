import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../state/app_state.dart';
import '../../widgets/common.dart';
import '../server_setup_screen.dart';

/// Profile / sign-out sheet reachable from every dashboard's avatar button.
Future<void> showAccountSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    builder: (context) {
      final user = appState.user;
      final theme = Theme.of(context);

      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: theme.colorScheme.primary,
                    child: Text(
                      user?.initials ?? '?',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 18,
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?.fullname ?? '',
                          style: theme.textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          '${roleLabel(user?.role ?? UserRole.student)} · ${user?.userId ?? ''}',
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.hintColor),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              ListTile(
                leading: const Icon(Icons.dns_outlined),
                title: const Text('Server address'),
                subtitle: Text(appState.baseUrl),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(context);
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const ServerSetupScreen(allowBack: true),
                    ),
                  );
                },
              ),
              const Divider(),
              ListTile(
                leading: Icon(Icons.logout, color: theme.colorScheme.error),
                title: Text('Sign out', style: TextStyle(color: theme.colorScheme.error)),
                onTap: () async {
                  final ok = await confirm(
                    context,
                    title: 'Sign out',
                    message: 'Sign out of CampusConnect+?',
                    confirmLabel: 'Sign out',
                  );
                  if (!ok) return;
                  await appState.signOut();
                  if (context.mounted) Navigator.pop(context);
                },
              ),
            ],
          ),
        ),
      );
    },
  );
}

/// The avatar button that opens [showAccountSheet].
class AccountButton extends StatelessWidget {
  const AccountButton({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(right: 12),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: () => showAccountSheet(context),
        child: CircleAvatar(
          radius: 18,
          backgroundColor: theme.colorScheme.primary,
          child: Text(
            appState.user?.initials ?? '?',
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
        ),
      ),
    );
  }
}
