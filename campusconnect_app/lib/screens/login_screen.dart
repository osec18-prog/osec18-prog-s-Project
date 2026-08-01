import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../widgets/common.dart';
import 'register_screen.dart';
import 'server_setup_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _identifier = TextEditingController();
  final _password = TextEditingController();

  UserRole _role = UserRole.student;
  bool _busy = false;
  bool _obscure = true;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  String get _identifierLabel {
    switch (_role) {
      case UserRole.student:
        return 'Student ID';
      case UserRole.professor:
        return 'Email or Employee ID';
      case UserRole.admin:
        return 'Admin username';
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _busy = true);
    try {
      await appState.signIn(
        role: _role,
        identifier: _identifier.text.trim(),
        password: _password.text,
      );
      // _Root in main.dart swaps to the right dashboard once state changes.
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
                    Image.asset('assets/images/logo.png', height: 88),
                    const SizedBox(height: 16),
                    Text(
                      'CampusConnect+',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    Text(
                      'AICS attendance portal',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor),
                    ),
                    const SizedBox(height: 26),
                    SegmentedButton<UserRole>(
                      segments: const [
                        ButtonSegment(
                          value: UserRole.student,
                          label: Text('Student'),
                          icon: Icon(Icons.school_outlined),
                        ),
                        ButtonSegment(
                          value: UserRole.professor,
                          label: Text('Professor'),
                          icon: Icon(Icons.badge_outlined),
                        ),
                        ButtonSegment(
                          value: UserRole.admin,
                          label: Text('Admin'),
                          icon: Icon(Icons.shield_outlined),
                        ),
                      ],
                      selected: {_role},
                      showSelectedIcon: false,
                      onSelectionChanged: (selection) =>
                          setState(() => _role = selection.first),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      controller: _identifier,
                      autocorrect: false,
                      decoration: InputDecoration(
                        labelText: _identifierLabel,
                        prefixIcon: const Icon(Icons.person_outline),
                      ),
                      validator: (value) =>
                          (value ?? '').trim().isEmpty ? 'Required.' : null,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _password,
                      obscureText: _obscure,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                      validator: (value) =>
                          (value ?? '').isEmpty ? 'Required.' : null,
                      onFieldSubmitted: (_) => _submit(),
                    ),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text('Sign in as ${roleLabel(_role)}'),
                    ),
                    if (_role == UserRole.student) ...[
                      const SizedBox(height: 6),
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => const RegisterScreen(),
                                  ),
                                ),
                        child: const Text('New student? Create an account'),
                      ),
                    ],
                    const SizedBox(height: 10),
                    TextButton.icon(
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => const ServerSetupScreen(allowBack: true),
                        ),
                      ),
                      icon: const Icon(Icons.dns_outlined, size: 18),
                      label: Text('Server: ${appState.baseUrl}'),
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
