import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/check_in.dart';
import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../models/workspace.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';

class OccurrenceScreen extends StatefulWidget {
  final String occurrenceId;
  const OccurrenceScreen({super.key, required this.occurrenceId});

  @override
  State<OccurrenceScreen> createState() => _OccurrenceScreenState();
}

class _OccurrenceScreenState extends State<OccurrenceScreen> {
  Occurrence? _occurrence;
  Series? _series;
  Workspace? _workspace;
  CheckIn? _myCheckIn;
  List<CheckIn>? _allCheckIns;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  bool get _canManage {
    final ws = _workspace;
    if (ws == null) return false;
    final role = ws.memberRoles[_uid];
    return role == 'organizer' || role == 'teacher';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiService>();
      final occ = await api.getOccurrence(widget.occurrenceId);
      final results = await Future.wait([
        api.getSeries(occ.seriesId),
        api.getWorkspace(occ.workspaceId),
        api.getMyCheckIn(widget.occurrenceId),
      ]);
      final ws = results[1] as Workspace;
      final role = ws.memberRoles[_uid];
      List<CheckIn>? allCheckIns;
      if (role == 'organizer' || role == 'teacher') {
        allCheckIns = await api.listCheckIns(widget.occurrenceId);
      }
      if (mounted) {
        setState(() {
          _occurrence = occ;
          _series = results[0] as Series;
          _workspace = ws;
          _myCheckIn = results[2] as CheckIn?;
          _allCheckIns = allCheckIns;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _checkIn() async {
    try {
      await context.read<ApiService>().upsertCheckIn(
          widget.occurrenceId, 'confirmed');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _undoCheckIn() async {
    final ci = _myCheckIn;
    if (ci == null) return;
    try {
      await context.read<ApiService>().deleteCheckIn(ci.checkInId);
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _updateStatus(String status) async {
    try {
      await context.read<ApiService>().updateOccurrence(
          widget.occurrenceId, {'status': status});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _toggleCheckIn(bool enable) async {
    try {
      await context.read<ApiService>().updateOccurrence(
          widget.occurrenceId, {'enable_check_in': enable});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _editOverrides() async {
    final occ = _occurrence;
    if (occ == null) return;
    final titleCtrl =
        TextEditingController(text: occ.overrides?.title ?? '');
    final locationCtrl =
        TextEditingController(text: occ.effectiveLocation ?? '');
    final linkCtrl =
        TextEditingController(text: occ.overrides?.onlineLink ?? '');
    final notesCtrl =
        TextEditingController(text: occ.overrides?.notes ?? '');

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Occurrence'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: titleCtrl,
                  decoration: const InputDecoration(labelText: 'Title')),
              const SizedBox(height: 12),
              TextField(
                  controller: locationCtrl,
                  decoration: const InputDecoration(labelText: 'Location')),
              const SizedBox(height: 12),
              TextField(
                  controller: linkCtrl,
                  decoration: const InputDecoration(labelText: 'Online Link')),
              const SizedBox(height: 12),
              TextField(
                  controller: notesCtrl,
                  decoration: const InputDecoration(labelText: 'Notes'),
                  maxLines: 3),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () {
                Navigator.pop(ctx, {
                  'overrides': {
                    'title': titleCtrl.text,
                    'location': locationCtrl.text,
                    'online_link': linkCtrl.text,
                    'notes': notesCtrl.text,
                  },
                });
              },
              child: const Text('Save')),
        ],
      ),
    );
    if (result == null) return;
    try {
      await context
          .read<ApiService>()
          .updateOccurrence(widget.occurrenceId, result);
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
          body: const Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final occ = _occurrence!;
    final series = _series!;
    final cs = Theme.of(context).colorScheme;
    final dt = occ.scheduledDateTime.toLocal();
    final effectiveLocation = occ.effectiveLocation ?? series.defaultLocation;
    final effectiveLink =
        occ.effectiveOnlineLink ?? series.defaultOnlineLink;
    final duration =
        occ.overrides?.durationMinutes ?? series.defaultDurationMinutes;
    final statusColor = _statusColorFor(occ.status);

    return Scaffold(
      appBar: AppBar(
        title: Text(occ.effectiveTitle.isNotEmpty
            ? occ.effectiveTitle
            : series.title),
        actions: [
          if (_canManage)
            IconButton(
                onPressed: _editOverrides, icon: const Icon(Icons.edit)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
          children: [
            // Date hero card
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        color: cs.primaryContainer,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(DateFormat('d').format(dt),
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 20,
                                  color: cs.onPrimaryContainer)),
                          Text(DateFormat('MMM').format(dt),
                              style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w500,
                                  color: cs.onPrimaryContainer)),
                        ],
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(DateFormat('EEEE').format(dt),
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600, fontSize: 15)),
                          Text(DateFormat('MMM d, yyyy  HH:mm').format(dt),
                              style: TextStyle(
                                  fontSize: 13, color: cs.onSurfaceVariant)),
                          if (duration != null)
                            Text('$duration min',
                                style: TextStyle(
                                    fontSize: 12, color: cs.onSurfaceVariant)),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: statusColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Text(occ.status,
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: statusColor)),
                    ),
                  ],
                ),
              ),
            ),

            // Location & link
            if (effectiveLocation != null || effectiveLink != null) ...[
              const SizedBox(height: 8),
              Card(
                child: Column(
                  children: [
                    if (effectiveLocation != null)
                      ListTile(
                        leading: Icon(Icons.location_on_outlined, size: 20,
                            color: cs.onSurfaceVariant),
                        title: Text(effectiveLocation,
                            style: const TextStyle(fontSize: 14)),
                      ),
                    if (effectiveLocation != null && effectiveLink != null)
                      Divider(height: 1, indent: 56,
                          color: cs.outlineVariant.withValues(alpha: 0.4)),
                    if (effectiveLink != null)
                      ListTile(
                        leading: Icon(Icons.videocam_outlined, size: 20,
                            color: cs.primary),
                        title: Text('Join online meeting',
                            style: TextStyle(fontSize: 14, color: cs.primary)),
                        trailing: Icon(Icons.open_in_new, size: 16,
                            color: cs.onSurfaceVariant),
                        onTap: () => launchUrl(Uri.parse(effectiveLink)),
                      ),
                  ],
                ),
              ),
            ],

            // Notes
            if (occ.effectiveNotes != null &&
                occ.effectiveNotes!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.notes, size: 16, color: cs.onSurfaceVariant),
                          const SizedBox(width: 8),
                          Text('Notes',
                              style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  color: cs.onSurfaceVariant)),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(occ.effectiveNotes!,
                          style: const TextStyle(fontSize: 14)),
                    ],
                  ),
                ),
              ),
            ],

            // Check-in section
            if (occ.enableCheckIn) ...[
              const SizedBox(height: 12),
              if (_myCheckIn == null || _myCheckIn!.status != 'confirmed')
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _checkIn,
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Check In'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(44),
                    ),
                  ),
                )
              else
                Card(
                  color: Colors.green.shade50,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    child: Row(
                      children: [
                        const Icon(Icons.check_circle,
                            color: Colors.green, size: 22),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Text('Checked in',
                              style: TextStyle(
                                  fontWeight: FontWeight.w500,
                                  color: Colors.green)),
                        ),
                        TextButton(
                            onPressed: _undoCheckIn,
                            child: const Text('Undo')),
                      ],
                    ),
                  ),
                ),
            ],

            // Manager controls
            if (_canManage) ...[
              const SizedBox(height: 16),
              _sectionLabel('Manage', cs),
              const SizedBox(height: 6),
              Card(
                child: Column(
                  children: [
                    // Status controls
                    if (occ.status == 'scheduled')
                      Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Expanded(
                              child: FilledButton(
                                onPressed: () => _updateStatus('completed'),
                                child: const Text('Complete'),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: OutlinedButton(
                                onPressed: () => _updateStatus('cancelled'),
                                child: const Text('Cancel'),
                              ),
                            ),
                          ],
                        ),
                      ),
                    SwitchListTile(
                      title: const Text('Enable Check-in',
                          style: TextStyle(fontSize: 14)),
                      value: occ.enableCheckIn,
                      onChanged: (v) => _toggleCheckIn(v),
                    ),
                  ],
                ),
              ),
            ],

            // All check-ins (organizer/teacher)
            if (_canManage && _allCheckIns != null && _allCheckIns!.isNotEmpty) ...[
              const SizedBox(height: 16),
              _sectionLabel('Check-ins (${_allCheckIns!.length})', cs),
              const SizedBox(height: 6),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: _allCheckIns!.asMap().entries.map((entry) {
                    final ci = entry.value;
                    final isLast = entry.key == _allCheckIns!.length - 1;
                    return Column(
                      children: [
                        ListTile(
                          leading: _checkInIcon(ci.status),
                          title: Text(
                              ci.displayName ?? ci.userId.substring(0, 8),
                              style: const TextStyle(fontSize: 14)),
                          subtitle: ci.note != null
                              ? Text(ci.note!,
                                  style: const TextStyle(fontSize: 12))
                              : null,
                          trailing: Text(ci.status,
                              style: TextStyle(
                                  fontSize: 12, color: cs.onSurfaceVariant)),
                        ),
                        if (!isLast)
                          Divider(height: 1, indent: 56,
                              color: cs.outlineVariant.withValues(alpha: 0.4)),
                      ],
                    );
                  }).toList(),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(String text, ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Text(text,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
            color: cs.onSurfaceVariant,
          )),
    );
  }

  Color _statusColorFor(String status) {
    return switch (status) {
      'scheduled' => Colors.blue,
      'completed' => Colors.green,
      'cancelled' => Colors.grey,
      'rescheduled' => Colors.orange,
      _ => Colors.grey,
    };
  }

  Widget _checkInIcon(String status) {
    return switch (status) {
      'confirmed' =>
        const Icon(Icons.check_circle, color: Colors.green, size: 20),
      'declined' => const Icon(Icons.cancel, color: Colors.red, size: 20),
      'missed' =>
        const Icon(Icons.remove_circle, color: Colors.orange, size: 20),
      _ =>
        const Icon(Icons.hourglass_empty, color: Colors.grey, size: 20),
    };
  }
}
