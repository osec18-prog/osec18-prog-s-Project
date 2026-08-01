import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';

/// First-run screen: point the app at the machine running app.py.
class ServerSetupScreen extends StatefulWidget {
  const ServerSetupScreen({super.key, this.allowBack = false});

  final bool allowBack;

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _controller =
      TextEditingController(text: appState.baseUrl.isEmpty ? 'http://' : appState.baseUrl);

  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _busy = true);
    final address = _controller.text.trim();

    try {
      // Verify before saving so a typo cannot lock the user on a dead address.
      await ApiClient().ping(candidateBaseUrl: address);
      await appState.setServer(address);

      if (!mounted) return;
      showSuccess(context, 'Connected to the CampusConnect+ server.');
      if (widget.allowBack) Navigator.pop(context);
    } catch (error) {
      if (mounted) showError(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: widget.allowBack ? AppBar(title: const Text('Server address')) : null,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Image.asset('assets/images/logo.png', height: 96),
                    const SizedBox(height: 20),
                    Text(
                      'Connect to your campus server',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Enter the address of the computer running the CampusConnect+ '
                      'server (app.py).',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor),
                    ),
                    const SizedBox(height: 24),
                    TextFormField(
                      controller: _controller,
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      decoration: const InputDecoration(
                        labelText: 'Server address',
                        hintText: 'http://192.168.1.5:5000',
                        prefixIcon: Icon(Icons.dns_outlined),
                      ),
                      validator: (value) {
                        final text = (value ?? '').trim();
                        if (text.isEmpty || text == 'http://') {
                          return 'Enter the server address.';
                        }
                        return null;
                      },
                      onFieldSubmitted: (_) => _connect(),
                    ),
                    const SizedBox(height: 18),
                    FilledButton.icon(
                      onPressed: _busy ? null : _connect,
                      icon: _busy
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.link),
                      label: Text(_busy ? 'Connecting…' : 'Connect'),
                    ),
                    const SizedBox(height: 24),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Icon(Icons.help_outline,
                                    size: 18, color: theme.colorScheme.primary),
                                const SizedBox(width: 8),
                                Text(
                                  'Where do I find the address?',
                                  style: theme.textTheme.titleSmall
                                      ?.copyWith(fontWeight: FontWeight.w700),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            _Hint(
                              text: 'On the server PC run '
                                  '"python app.py" — it listens on port 5000.',
                            ),
                            _Hint(
                              text: 'Run "ipconfig" on that PC and use its IPv4 address, '
                                  'e.g. http://192.168.1.5:5000',
                            ),
                            _Hint(
                              text: 'Phone and PC must be on the same Wi-Fi network.',
                            ),
                            _Hint(
                              text: 'Android emulator: use http://10.0.2.2:5000',
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6, right: 8),
            child: Icon(Icons.circle, size: 5, color: theme.hintColor),
          ),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
          ),
        ],
      ),
    );
  }
}
