import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/check_in.dart';
import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../models/room.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../shared/formatting/timezone_helpers.dart';
import '../../shared/widgets/resource_links.dart';

class OccurrenceScreen extends StatefulWidget {
  final String occurrenceId;
  const OccurrenceScreen({super.key, required this.occurrenceId});

  @override
  State<OccurrenceScreen> createState() => _OccurrenceScreenState();
}

class _OccurrenceScreenState extends State<OccurrenceScreen> {
  Occurrence? _occurrence;
  Series? _series;
  Room? _room;
  CheckIn? _myCheckIn;
  List<CheckIn>? _allCheckIns;
  bool _loading = true;
  String? _error;
  String _deviceTz = 'UTC';

  // Share state
  bool _shareOpen = false;
  bool _includeInvite = false;
  String? _inviteId;
  bool _inviteLoading = false;
  bool _shareCopied = false;

  @override
  void initState() {
    super.initState();
    _loadDeviceTz();
    _load();
  }

  Future<void> _loadDeviceTz() async {
    final tz = await getDeviceTimezone();
    if (mounted) setState(() => _deviceTz = tz);
  }

  @override
  void didUpdateWidget(OccurrenceScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.occurrenceId != widget.occurrenceId) {
      _load();
    }
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  bool get _canManage {
    final room = _room;
    if (room == null) return false;
    final role = room.memberRoles[_uid];
    return role == 'organizer' || role == 'teacher';
  }

  bool get _isOrganizer {
    final room = _room;
    if (room == null) return false;
    return room.memberRoles[_uid] == 'organizer';
  }

  String get _shareUrl {
    final base = 'https://small-group.ai/occurrences/${widget.occurrenceId}/summary';
    return _inviteId != null ? '$base?invite=$_inviteId' : base;
  }

  Future<void> _toggleInvite() async {
    if (_includeInvite) {
      setState(() {
        _includeInvite = false;
        _inviteId = null;
      });
      return;
    }
    setState(() => _inviteLoading = true);
    try {
      final api = context.read<ApiService>();
      final invite = await api.createInvite(_room!.roomId, 'participant');
      if (mounted) {
        setState(() {
          _inviteId = invite['invite_id'] as String;
          _includeInvite = true;
        });
      }
    } catch (e) {
      debugPrint('ERROR: Failed to create invite: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to create invite: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _inviteLoading = false);
    }
  }

  Future<void> _copyShareLink() async {
    await Clipboard.setData(ClipboardData(text: _shareUrl));
    setState(() => _shareCopied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _shareCopied = false);
    });
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
        api.getRoom(occ.roomId),
        api.getMyCheckIn(widget.occurrenceId),
      ]);
      final room = results[1] as Room;
      final role = room.memberRoles[_uid];
      List<CheckIn>? allCheckIns;
      if (role == 'organizer' || role == 'teacher') {
        allCheckIns = await api.listCheckIns(widget.occurrenceId);
      }
      if (mounted) {
        setState(() {
          _occurrence = occ;
          _series = results[0] as Series;
          _room = room;
          _myCheckIn = results[2] as CheckIn?;
          _allCheckIns = allCheckIns;
        });
      }
    } catch (e) {
      debugPrint('ERROR: Failed to load occurrence: $e');
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
      debugPrint('WARN: Failed to check in: $e');
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
      debugPrint('WARN: Failed to undo check-in: $e');
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
      debugPrint('ERROR: Failed to toggle check-in: $e');
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
                  'location': locationCtrl.text.trim().isNotEmpty
                      ? locationCtrl.text.trim()
                      : null,
                  'overrides': {
                    'title': titleCtrl.text,
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
      debugPrint('ERROR: Failed to update occurrence overrides: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _editHost(Occurrence occ) async {
    final series = _series;
    final rotationList = series?.hostRotation ?? [];
    final initialValue = occ.host ?? '';
    String selectedHost = initialValue;

    final newHost = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Host'),
        content: Autocomplete<String>(
          initialValue: TextEditingValue(text: initialValue),
          optionsBuilder: (textEditingValue) {
            if (rotationList.isEmpty) return const Iterable<String>.empty();
            final query = textEditingValue.text.toLowerCase();
            if (query.isEmpty) return rotationList;
            return rotationList.where(
                (h) => h.toLowerCase().contains(query));
          },
          fieldViewBuilder: (ctx, controller, focusNode, onSubmitted) {
            return TextField(
              controller: controller,
              focusNode: focusNode,
              decoration: InputDecoration(
                labelText: 'Host Name',
                hintText: rotationList.isNotEmpty
                    ? 'Type or select a host'
                    : 'Team A, Alice, etc.',
              ),
              onChanged: (v) => selectedHost = v,
              onSubmitted: (_) => onSubmitted(),
              autofocus: true,
            );
          },
          onSelected: (value) => selectedHost = value,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, selectedHost),
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (newHost == null) return;
    final trimmed = newHost.trim();
    try {
      final updates = <String, dynamic>{
        'host': trimmed.isNotEmpty ? trimmed : null,
      };
      // Auto-sync location in host_and_location mode
      if (series?.hostRotationMode == 'host_and_location' && trimmed.isNotEmpty) {
        final address = series?.hostAddresses?[trimmed];
        updates['location'] = address ?? series?.defaultLocation;
      }
      await context.read<ApiService>().updateOccurrence(
        widget.occurrenceId,
        updates,
      );
      await _load();

      // Prompt to continue rotation if host is in the rotation list
      if (mounted && trimmed.isNotEmpty && rotationList.contains(trimmed)) {
        // Update the occurrence reference after reload
        final updatedOcc = _occurrence;
        if (updatedOcc != null) {
          await _repopulateRotation(updatedOcc);
        }
      }
    } catch (e) {
      debugPrint('ERROR: Failed to edit host: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _repopulateRotation(Occurrence occ) async {
    final cs = Theme.of(context).colorScheme;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Re-populate rotation?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'This will update all upcoming occurrences to continue the rotation from:',
              style: TextStyle(fontSize: 14),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: cs.primaryContainer,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Icon(Icons.person, color: cs.onPrimaryContainer),
                  const SizedBox(width: 8),
                  Text(
                    occ.host ?? 'No host',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: cs.onPrimaryContainer,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Previously assigned hosts will be replaced.',
              style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Re-populate'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      final result = await context.read<ApiService>().repopulateRotation(
        occ.seriesId,
        occ.occurrenceId,
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Updated ${result['updated_count']} occurrences'),
            backgroundColor: Colors.green,
          ),
        );
        _load();
      }
    } catch (e) {
      debugPrint('ERROR: Failed to repopulate rotation: $e');
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
    final room = _room!;
    final cs = Theme.of(context).colorScheme;
    final dt = occ.scheduledDateTime.toLocal();
    final showDualTz = !timezonesMatch(room.timezone, _deviceTz);
    final effectiveLocation = series.hasLocation
        ? (occ.effectiveLocation ?? series.defaultLocation)
        : occ.overrides?.location;
    final effectiveLink =
        occ.effectiveOnlineLink ?? series.defaultOnlineLink;
    final duration =
        occ.overrides?.durationMinutes ?? series.defaultDurationMinutes;
    return Scaffold(
      appBar: AppBar(
        title: Text(occ.effectiveTitle.isNotEmpty
            ? occ.effectiveTitle
            : series.title),
        actions: [
          if (occ.prevOccurrenceId != null)
            IconButton(
              icon: const Icon(Icons.chevron_left),
              onPressed: () => context.go('/occurrences/${occ.prevOccurrenceId}'),
            ),
          if (occ.nextOccurrenceId != null)
            IconButton(
              icon: const Icon(Icons.chevron_right),
              onPressed: () => context.go('/occurrences/${occ.nextOccurrenceId}'),
            ),
          if (_canManage)
            IconButton(
                onPressed: _editOverrides, icon: const Icon(Icons.edit)),
        ],
      ),
      body: GestureDetector(
        onHorizontalDragEnd: (details) {
          if (details.primaryVelocity != null) {
            if (details.primaryVelocity! < -200 && occ.nextOccurrenceId != null) {
              context.go('/occurrences/${occ.nextOccurrenceId}');
            } else if (details.primaryVelocity! > 200 && occ.prevOccurrenceId != null) {
              context.go('/occurrences/${occ.prevOccurrenceId}');
            }
          }
        },
        child: RefreshIndicator(
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
                          Text(
                              showDualTz
                                  ? '${DateFormat('MMM d, yyyy  HH:mm').format(dt)} (${dt.timeZoneName})'
                                  : DateFormat('MMM d, yyyy  HH:mm').format(dt),
                              style: TextStyle(
                                  fontSize: 13, color: cs.onSurfaceVariant)),
                          if (showDualTz)
                            Text(
                                'Room: ${room.timezone.split('/').last.replaceAll('_', ' ')}',
                                style: TextStyle(
                                    fontSize: 11, color: cs.onSurfaceVariant)),
                          if (duration != null)
                            Text('$duration min',
                                style: TextStyle(
                                    fontSize: 12, color: cs.onSurfaceVariant)),
                        ],
                      ),
                    ),
                    // status badge hidden – issue #114
                  ],
                ),
              ),
            ),

            // Host card
            if (occ.host != null || (_canManage && series.hostRotation != null && series.hostRotation!.isNotEmpty)) ...[
              const SizedBox(height: 8),
              Card(
                child: ListTile(
                  leading: CircleAvatar(
                    radius: 20,
                    backgroundColor: cs.primaryContainer,
                    child: Icon(Icons.person, size: 20, color: cs.onPrimaryContainer),
                  ),
                  title: const Text('Host', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  subtitle: Text(
                    occ.host ?? 'Set host',
                    style: TextStyle(
                      fontSize: 14,
                      color: occ.host != null ? null : cs.onSurfaceVariant,
                    ),
                  ),
                  trailing: _canManage
                      ? IconButton(
                          icon: const Icon(Icons.edit, size: 18),
                          onPressed: () => _editHost(occ),
                        )
                      : null,
                ),
              ),
            ],

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
            ] else if (!series.hasLocation && effectiveLocation == null && _canManage) ...[
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _editOverrides,
                icon: const Icon(Icons.add_location_alt, size: 18),
                label: const Text('+ Add location'),
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
                      MarkdownBody(
                        data: occ.effectiveNotes!,
                        softLineBreak: true,
                        onTapLink: (text, href, title) {
                          if (href != null) launchUrl(Uri.parse(href));
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ],

            // Resources (below notes)
            const SizedBox(height: 12),
            ResourceLinksSection(
              links: occ.links,
              canEdit: _canManage,
              onSave: (links) async {
                await context.read<ApiService>().updateOccurrence(
                    widget.occurrenceId, {'links': links});
                _load();
              },
            ),

            // Check-in section
            if (occ.enableCheckIn) ...[
              const SizedBox(height: 12),
              if (_myCheckIn == null || _myCheckIn!.status != 'confirmed')
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _checkIn,
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Done'),
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
                          child: Text('Done ✓',
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
                    if (series.enableDone)
                      SwitchListTile(
                        title: const Text('Show "Done" button',
                            style: TextStyle(fontSize: 14)),
                        value: occ.enableCheckIn,
                        onChanged: (v) => _toggleCheckIn(v),
                      ),
                    if (series.hostRotationMode != 'none' &&
                        occ.host != null &&
                        (series.hostRotation ?? []).contains(occ.host)) ...[
                      const Divider(height: 1),
                      ListTile(
                        leading: Icon(Icons.refresh, color: cs.primary),
                        title: const Text('Re-populate rotation from here',
                            style: TextStyle(fontSize: 14)),
                        subtitle: const Text(
                            'Update upcoming occurrences to continue rotation from this host',
                            style: TextStyle(fontSize: 12)),
                        onTap: () => _repopulateRotation(occ),
                      ),
                    ],
                    const Divider(height: 1),
                    ListTile(
                      leading: const Icon(Icons.delete_outline, color: Colors.red),
                      title: const Text('Delete occurrence',
                          style: TextStyle(color: Colors.red)),
                      onTap: () async {
                        final confirmed = await showDialog<bool>(
                          context: context,
                          builder: (ctx) => AlertDialog(
                            title: const Text('Delete occurrence?'),
                            content: const Text('This cannot be undone.'),
                            actions: [
                              TextButton(
                                  onPressed: () => Navigator.pop(ctx, false),
                                  child: const Text('Cancel')),
                              TextButton(
                                  onPressed: () => Navigator.pop(ctx, true),
                                  child: const Text('Delete',
                                      style: TextStyle(color: Colors.red))),
                            ],
                          ),
                        );
                        if (confirmed == true && mounted) {
                          await context
                              .read<ApiService>()
                              .deleteOccurrence(widget.occurrenceId);
                          if (mounted) Navigator.pop(context);
                        }
                      },
                    ),
                  ],
                ),
              ),
            ],

            // All check-ins (organizer/teacher)
            if (_canManage && _allCheckIns != null && _allCheckIns!.isNotEmpty) ...[
              const SizedBox(height: 16),
              _sectionLabel('Completions (${_allCheckIns!.length})', cs),
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

            // Share
            if (effectiveLocation != null || effectiveLink != null) ...[
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _sectionLabel('Share', cs),
                  OutlinedButton(
                    onPressed: () => setState(() => _shareOpen = !_shareOpen),
                    child: Text(_shareOpen ? 'Close' : 'Share'),
                  ),
                ],
              ),
              if (!_shareOpen)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    'Share meeting details with participants.',
                    style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
                  ),
                ),
              if (_shareOpen) ...[
                const SizedBox(height: 6),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // URL + copy
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                _shareUrl,
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 8),
                            OutlinedButton(
                              onPressed: _copyShareLink,
                              child: Text(_shareCopied ? 'Copied!' : 'Copy'),
                            ),
                          ],
                        ),
                        // Include invite toggle (organizer only)
                        if (_isOrganizer) ...[
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              SizedBox(
                                height: 24,
                                width: 24,
                                child: _inviteLoading
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(strokeWidth: 2),
                                      )
                                    : Checkbox(
                                        value: _includeInvite,
                                        onChanged: (_) => _toggleInvite(),
                                      ),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Include invite link (joins as participant)',
                                style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
                              ),
                            ],
                          ),
                        ],
                        const SizedBox(height: 8),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: () => context.push(
                                '/occurrences/${widget.occurrenceId}/summary'),
                            icon: const Icon(Icons.open_in_new, size: 16),
                            label: const Text('Preview'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ],
        ),
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
