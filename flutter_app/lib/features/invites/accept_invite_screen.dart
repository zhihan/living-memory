import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../services/api_service.dart';
import '../../services/auth_service.dart';

class AcceptInviteScreen extends StatefulWidget {
  final String inviteId;
  const AcceptInviteScreen({super.key, required this.inviteId});

  @override
  State<AcceptInviteScreen> createState() => _AcceptInviteScreenState();
}

class _AcceptInviteScreenState extends State<AcceptInviteScreen> {
  bool _loading = false;
  String? _error;

  Future<void> _accept() async {
    final auth = context.read<AuthService>();
    if (!auth.isSignedIn) {
      // Sign in first
      try {
        await auth.signInWithGoogle();
      } catch (e) {
        if (mounted) setState(() => _error = 'Sign-in failed: $e');
        return;
      }
    }

    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result =
          await context.read<ApiService>().acceptInvite(widget.inviteId);
      if (mounted) {
        final workspaceId = result['workspace_id'] as String;
        context.go('/workspaces/$workspaceId');
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Accept Invite')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.mail_outline, size: 48),
              const SizedBox(height: 16),
              const Text('You have been invited to join a workspace.'),
              const SizedBox(height: 24),
              if (_loading)
                const CircularProgressIndicator()
              else
                FilledButton(
                    onPressed: _accept,
                    child: const Text('Accept Invite')),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!,
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.error)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
