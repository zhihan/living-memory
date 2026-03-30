import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/workspace.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  List<Workspace>? _workspaces;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiService>();
      final workspaces = await api.listWorkspaces();
      if (mounted) setState(() => _workspaces = workspaces);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createWorkspace() async {
    final title = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final controller = TextEditingController();
        return AlertDialog(
          title: const Text('New Workspace'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(labelText: 'Title'),
            autofocus: true,
            onSubmitted: (v) => Navigator.pop(ctx, v),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, controller.text),
                child: const Text('Create')),
          ],
        );
      },
    );
    if (title == null || title.trim().isEmpty) return;
    try {
      await context.read<ApiService>().createWorkspace(title: title.trim());
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Workspaces'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthService>().signOut(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _createWorkspace,
        child: const Icon(Icons.add),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const SizedBox(height: 8),
            FilledButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    final workspaces = _workspaces ?? [];
    if (workspaces.isEmpty) {
      return const Center(child: Text('No workspaces yet. Tap + to create one.'));
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        itemCount: workspaces.length,
        itemBuilder: (context, index) {
          final ws = workspaces[index];
          return ListTile(
            title: Text(ws.title),
            subtitle: Text(ws.timezone),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.push('/workspaces/${ws.workspaceId}'),
          );
        },
      ),
    );
  }
}
