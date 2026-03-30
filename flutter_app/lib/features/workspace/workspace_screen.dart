import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/series.dart';
import '../../models/workspace.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import 'create_series_dialog.dart';

class WorkspaceScreen extends StatefulWidget {
  final String workspaceId;
  const WorkspaceScreen({super.key, required this.workspaceId});

  @override
  State<WorkspaceScreen> createState() => _WorkspaceScreenState();
}

class _WorkspaceScreenState extends State<WorkspaceScreen> {
  Workspace? _workspace;
  List<Series>? _series;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  String? _roleInWorkspace(Workspace ws) => ws.memberRoles[_uid];

  bool _isOrganizer(Workspace ws) => _roleInWorkspace(ws) == 'organizer';

  bool _canManageSeries(Workspace ws) {
    final role = _roleInWorkspace(ws);
    return role == 'organizer' || role == 'teacher';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiService>();
      final results = await Future.wait([
        api.getWorkspace(widget.workspaceId),
        api.listSeries(widget.workspaceId),
      ]);
      if (mounted) {
        setState(() {
          _workspace = results[0] as Workspace;
          _series = results[1] as List<Series>;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editTitle() async {
    final ws = _workspace;
    if (ws == null || !_isOrganizer(ws)) return;
    final controller = TextEditingController(text: ws.title);
    final newTitle = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Title'),
        content: TextField(controller: controller, autofocus: true,
            onSubmitted: (v) => Navigator.pop(ctx, v)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, controller.text),
              child: const Text('Save')),
        ],
      ),
    );
    if (newTitle == null || newTitle.trim().isEmpty || newTitle.trim() == ws.title) return;
    try {
      await context.read<ApiService>().updateWorkspace(
          widget.workspaceId, {'title': newTitle.trim()});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _createInvite() async {
    try {
      final invite = await context
          .read<ApiService>()
          .createInvite(widget.workspaceId, 'participant');
      final inviteId = invite['invite_id'];
      final link =
          'https://living-memories-488001.web.app/invites/$inviteId';
      if (mounted) {
        await Clipboard.setData(ClipboardData(text: link));
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Invite link copied!')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _createSeries() async {
    final body = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => const CreateSeriesDialog(),
    );
    if (body == null) return;
    try {
      await context.read<ApiService>().createSeries(widget.workspaceId, body);
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
    if (_loading) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final ws = _workspace!;
    final series = _series ?? [];

    return Scaffold(
      appBar: AppBar(
        title: GestureDetector(
          onTap: _isOrganizer(ws) ? _editTitle : null,
          child: Text(ws.title),
        ),
      ),
      floatingActionButton: _canManageSeries(ws)
          ? FloatingActionButton(
              onPressed: _createSeries,
              child: const Icon(Icons.add),
            )
          : null,
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          children: [
            // Workspace info
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Timezone: ${ws.timezone}',
                      style: Theme.of(context).textTheme.bodyMedium),
                  if (ws.description != null && ws.description!.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(ws.description!),
                    ),
                ],
              ),
            ),

            // Members section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  Text('Members',
                      style: Theme.of(context).textTheme.titleMedium),
                  const Spacer(),
                  if (_isOrganizer(ws))
                    TextButton.icon(
                      onPressed: _createInvite,
                      icon: const Icon(Icons.person_add, size: 18),
                      label: const Text('Invite'),
                    ),
                ],
              ),
            ),
            ...ws.memberRoles.entries.map((e) {
              final profile = ws.memberProfiles[e.key];
              final name = profile?['display_name'] ?? e.key.substring(0, 8);
              return ListTile(
                dense: true,
                leading: const Icon(Icons.person, size: 20),
                title: Text(name),
                trailing: Chip(
                  label: Text(e.value, style: const TextStyle(fontSize: 11)),
                  visualDensity: VisualDensity.compact,
                ),
              );
            }),

            const Divider(),

            // Series section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text('Series',
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            if (series.isEmpty)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('No series yet.'),
              ),
            ...series.map((s) => ListTile(
                  title: Text(s.title),
                  subtitle: Text(s.scheduleDescription),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => context.push('/series/${s.seriesId}'),
                )),
          ],
        ),
      ),
    );
  }
}
