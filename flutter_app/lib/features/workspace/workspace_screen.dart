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
    final cs = Theme.of(context).colorScheme;

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
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 80),
          children: [
            // Workspace info
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    Icon(Icons.public, size: 16, color: cs.onSurfaceVariant),
                    const SizedBox(width: 8),
                    Text(ws.timezone,
                        style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                    const Spacer(),
                    Icon(Icons.people_outline, size: 16, color: cs.onSurfaceVariant),
                    const SizedBox(width: 6),
                    Text('${ws.memberRoles.length} members',
                        style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                  ],
                ),
              ),
            ),
            if (ws.description != null && ws.description!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Text(ws.description!,
                      style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                ),
              ),
            ],

            // Members section
            const SizedBox(height: 16),
            _SectionHeader(
              icon: Icons.people_outline,
              title: 'Members',
              trailing: _isOrganizer(ws)
                  ? TextButton.icon(
                      onPressed: _createInvite,
                      icon: const Icon(Icons.person_add, size: 16),
                      label: const Text('Invite'),
                      style: TextButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        textStyle: const TextStyle(fontSize: 13),
                      ),
                    )
                  : null,
            ),
            const SizedBox(height: 6),
            Card(
              clipBehavior: Clip.antiAlias,
              child: Column(
                children: [
                  ...ws.memberRoles.entries.toList().asMap().entries.map((entry) {
                    final e = entry.value;
                    final isLast = entry.key == ws.memberRoles.length - 1;
                    final profile = ws.memberProfiles[e.key];
                    final name = profile?['display_name'] ?? e.key.substring(0, 8);
                    final isMe = e.key == _uid;
                    return Column(
                      children: [
                        ListTile(
                          leading: CircleAvatar(
                            radius: 16,
                            backgroundColor: cs.primaryContainer,
                            child: Text(
                              (name as String).isNotEmpty ? name[0].toUpperCase() : '?',
                              style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: cs.onPrimaryContainer),
                            ),
                          ),
                          title: Text(isMe ? '$name (You)' : name,
                              style: const TextStyle(fontSize: 14)),
                          trailing: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: e.value == 'organizer'
                                  ? cs.primaryContainer
                                  : cs.surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(e.value,
                                style: TextStyle(
                                    fontSize: 11,
                                    color: e.value == 'organizer'
                                        ? cs.onPrimaryContainer
                                        : cs.onSurfaceVariant)),
                          ),
                        ),
                        if (!isLast)
                          Divider(height: 1, indent: 56,
                              color: cs.outlineVariant.withValues(alpha: 0.4)),
                      ],
                    );
                  }),
                ],
              ),
            ),

            // Series section
            const SizedBox(height: 16),
            _SectionHeader(icon: Icons.event_repeat, title: 'Series'),
            const SizedBox(height: 6),
            if (series.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Center(
                    child: Column(
                      children: [
                        Icon(Icons.event_note, size: 32, color: cs.onSurfaceVariant),
                        const SizedBox(height: 8),
                        Text('No series yet',
                            style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13)),
                      ],
                    ),
                  ),
                ),
              ),
            ...series.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _seriesCard(s, cs),
                )),
          ],
        ),
      ),
    );
  }

  Widget _seriesCard(Series s, ColorScheme cs) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/series/${s.seriesId}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(s.title,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600, fontSize: 15)),
                  ),
                  Icon(Icons.chevron_right, size: 20, color: cs.onSurfaceVariant),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Icon(Icons.schedule, size: 14, color: cs.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text(s.scheduleDescription,
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                  if (s.defaultTime != null) ...[
                    Text(' at ${s.defaultTime}',
                        style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                  ],
                ],
              ),
              if (s.defaultLocation != null || s.defaultOnlineLink != null) ...[
                const SizedBox(height: 4),
                Row(
                  children: [
                    Icon(
                      s.defaultLocation != null
                          ? Icons.location_on_outlined
                          : Icons.link,
                      size: 14,
                      color: cs.onSurfaceVariant,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        s.defaultLocation ?? 'Online',
                        style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ],
              if (s.description != null && s.description!.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(s.description!,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  final Widget? trailing;

  const _SectionHeader({
    required this.icon,
    required this.title,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Row(
        children: [
          Icon(icon, size: 16, color: cs.onSurfaceVariant),
          const SizedBox(width: 6),
          Text(title,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
                color: cs.onSurfaceVariant,
              )),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
