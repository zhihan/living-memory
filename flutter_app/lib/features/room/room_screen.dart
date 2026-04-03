import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/series.dart';
import '../../models/room.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../shared/formatting/timezone_helpers.dart';
import '../../shared/widgets/resource_links.dart';
import 'create_series_dialog.dart';

class RoomScreen extends StatefulWidget {
  final String roomId;
  const RoomScreen({super.key, required this.roomId});

  @override
  State<RoomScreen> createState() => _RoomScreenState();
}

class _RoomScreenState extends State<RoomScreen> {
  Room? _room;
  List<Series>? _series;
  bool _loading = true;
  String? _error;
  String _deviceTz = 'UTC';

  // Telegram bot state
  Map<String, dynamic>? _tgBot;
  bool _tgLoading = true;
  String? _tgLinkCode;
  int _tgLinkExpiry = 0;
  Timer? _tgTimer;

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
  void dispose() {
    _tgTimer?.cancel();
    super.dispose();
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  String? _roleInRoom(Room room) => room.memberRoles[_uid];

  bool _isOrganizer(Room room) => _roleInRoom(room) == 'organizer';

  bool _canManageSeries(Room room) {
    final role = _roleInRoom(room);
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
        api.getRoom(widget.roomId),
        api.listSeries(widget.roomId),
      ]);
      if (mounted) {
        setState(() {
          _room = results[0] as Room;
          _series = results[1] as List<Series>;
        });
      }
      // Load telegram bot (non-blocking)
      api.getTelegramBot(widget.roomId).then((bot) {
        if (mounted) setState(() => _tgBot = bot);
      }).catchError((e) { debugPrint('Failed to load Telegram bot: $e'); }).whenComplete(() {
        if (mounted) setState(() => _tgLoading = false);
      });
    } catch (e) {
      debugPrint('ERROR: Failed to load room: $e');
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editTitle() async {
    final room = _room;
    if (room == null || !_isOrganizer(room)) return;
    final controller = TextEditingController(text: room.title);
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
    if (newTitle == null || newTitle.trim().isEmpty || newTitle.trim() == room.title) return;
    try {
      await context.read<ApiService>().updateRoom(
          widget.roomId, {'title': newTitle.trim()});
      _load();
    } catch (e) {
      debugPrint('ERROR: Failed to edit room title: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _editNotes(Room room) async {
    if (!_isOrganizer(room)) return;
    final controller = TextEditingController(text: room.description ?? '');
    final newNotes = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Notes'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 5,
          decoration: const InputDecoration(
            hintText: 'Add a description, resources, or notes for this room.',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, controller.text),
              child: const Text('Save')),
        ],
      ),
    );
    if (newNotes == null || newNotes.trim() == (room.description ?? '')) return;
    try {
      await context.read<ApiService>().updateRoom(
          widget.roomId, {'description': newNotes.trim()});
      _load();
    } catch (e) {
      debugPrint('ERROR: Failed to edit room notes: $e');
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
          .createInvite(widget.roomId, 'participant');
      final inviteId = invite['invite_id'];
      final link =
          'https://small-group.ai/invites/$inviteId';
      if (mounted) {
        await Clipboard.setData(ClipboardData(text: link));
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Invite link copied!')));
      }
    } catch (e) {
      debugPrint('WARN: Failed to create invite: $e');
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
      await context.read<ApiService>().createSeries(widget.roomId, body);
      _load();
    } catch (e) {
      debugPrint('ERROR: Failed to create series: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _connectTelegramBot(String token, String mode) async {
    try {
      final bot = await context
          .read<ApiService>()
          .connectTelegramBot(widget.roomId, token, mode: mode);
      if (mounted) setState(() => _tgBot = bot);
    } catch (e) {
      debugPrint('WARN: Failed to connect Telegram bot: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _updateTelegramBotMode(String mode) async {
    try {
      final bot = await context
          .read<ApiService>()
          .updateTelegramBotMode(widget.roomId, mode);
      if (mounted) setState(() => _tgBot = bot);
    } catch (e) {
      debugPrint('ERROR: Failed to update Telegram bot mode: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _disconnectTelegramBot() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Disconnect bot?'),
        content: const Text('Chat linking will stop.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Disconnect',
                  style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await context.read<ApiService>().deleteTelegramBot(widget.roomId);
      if (mounted) {
        _tgTimer?.cancel();
        setState(() {
          _tgBot = null;
          _tgLinkCode = null;
          _tgLinkExpiry = 0;
        });
      }
    } catch (e) {
      debugPrint('ERROR: Failed to disconnect Telegram bot: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _generateLinkCode() async {
    try {
      final result = await context
          .read<ApiService>()
          .generateTelegramLinkCode(widget.roomId);
      if (mounted) {
        setState(() {
          _tgLinkCode = result['code'] as String;
          _tgLinkExpiry = result['expires_in'] as int;
        });
        _tgTimer?.cancel();
        _tgTimer = Timer.periodic(const Duration(seconds: 1), (_) {
          if (!mounted) return;
          setState(() {
            _tgLinkExpiry--;
            if (_tgLinkExpiry <= 0) {
              _tgLinkCode = null;
              _tgLinkExpiry = 0;
              _tgTimer?.cancel();
            }
          });
        });
      }
    } catch (e) {
      debugPrint('WARN: Failed to generate Telegram link code: $e');
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

    final room = _room!;
    final series = _series ?? [];
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: GestureDetector(
          onTap: _isOrganizer(room) ? _editTitle : null,
          child: Text(room.title),
        ),
      ),
      floatingActionButton: _canManageSeries(room)
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
            // Room info
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    if (!timezonesMatch(room.timezone, _deviceTz)) ...[
                      Icon(Icons.public, size: 16, color: cs.onSurfaceVariant),
                      const SizedBox(width: 8),
                      Text(room.timezone,
                          style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                    ],
                    const Spacer(),
                    Icon(Icons.people_outline, size: 16, color: cs.onSurfaceVariant),
                    const SizedBox(width: 6),
                    Text('${room.memberRoles.length} members',
                        style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                  ],
                ),
              ),
            ),
            if (room.description != null && room.description!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Card(
                child: InkWell(
                  onTap: _isOrganizer(room) ? () => _editNotes(room) : null,
                  borderRadius: BorderRadius.circular(12),
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(room.description!,
                              style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                        ),
                        if (_isOrganizer(room))
                          Icon(Icons.edit, size: 16, color: cs.onSurfaceVariant),
                      ],
                    ),
                  ),
                ),
              ),
            ] else if (_isOrganizer(room)) ...[
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: () => _editNotes(room),
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Add notes'),
              ),
            ],

            // Series section (before Members, matching web layout)
            const SizedBox(height: 16),
            _SectionHeader(icon: Icons.event_repeat, title: 'Recurring Series'),
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

            // Resources (below series)
            const SizedBox(height: 12),
            ResourceLinksSection(
              links: room.links,
              canEdit: _isOrganizer(room),
              onSave: (links) async {
                await context.read<ApiService>().updateRoom(
                    widget.roomId, {'links': links});
                _load();
              },
            ),

            // Members section
            const SizedBox(height: 16),
            _SectionHeader(
              icon: Icons.people_outline,
              title: 'Members',
              trailing: _isOrganizer(room)
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
                  ...room.memberRoles.entries.toList().asMap().entries.map((entry) {
                    final e = entry.value;
                    final isLast = entry.key == room.memberRoles.length - 1;
                    final profile = room.memberProfiles[e.key];
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

            // Leave room (non-organizers)
            if (!_isOrganizer(room)) ...[
              const SizedBox(height: 12),
              Center(
                child: TextButton.icon(
                  icon: const Icon(Icons.logout, size: 18),
                  label: const Text('Leave room'),
                  style: TextButton.styleFrom(
                    foregroundColor: cs.error,
                  ),
                  onPressed: () async {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        title: const Text('Leave room?'),
                        content: const Text('You will lose access to this room.'),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, false),
                            child: const Text('Cancel'),
                          ),
                          FilledButton(
                            onPressed: () => Navigator.pop(ctx, true),
                            style: FilledButton.styleFrom(backgroundColor: cs.error),
                            child: const Text('Leave'),
                          ),
                        ],
                      ),
                    );
                    if (confirmed != true) return;
                    try {
                      await context.read<ApiService>().removeMember(room.roomId, _uid);
                      if (mounted) context.go('/');
                    } catch (e) {
                      debugPrint('ERROR: Failed to leave room: $e');
                      if (mounted) {
                        ScaffoldMessenger.of(context)
                            .showSnackBar(SnackBar(content: Text('Error: $e')));
                      }
                    }
                  },
                ),
              ),
            ],

            // Telegram bot (organizer only)
            if (_isOrganizer(room)) ...[
              const SizedBox(height: 16),
              _SectionHeader(
                  icon: Icons.smart_toy_outlined,
                  title: 'AI Assistant (Telegram)'),
              const SizedBox(height: 6),
              if (_tgLoading)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(20),
                    child: Center(
                        child: SizedBox(
                            width: 20,
                            height: 20,
                            child:
                                CircularProgressIndicator(strokeWidth: 2))),
                  ),
                )
              else if (_tgBot != null)
                _telegramBotCard(_tgBot!, cs)
              else
                _telegramConnectCard(cs),
            ],

            // Delete room (organizer only)
            if (_isOrganizer(room)) ...[
              const SizedBox(height: 24),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.delete_outline, color: Colors.red),
                  title: const Text('Delete room',
                      style: TextStyle(color: Colors.red)),
                  onTap: () async {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        title: const Text('Delete room?'),
                        content: const Text(
                            'This will delete the room and all its data. This cannot be undone.'),
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
                          .deleteRoom(widget.roomId);
                      if (mounted) context.go('/');
                    }
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _telegramConnectCard(ColorScheme cs) {
    final tokenController = TextEditingController();
    String selectedMode = 'read_only';
    bool connecting = false;

    return StatefulBuilder(
      builder: (context, setLocalState) => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: tokenController,
                decoration: const InputDecoration(
                  labelText: 'Bot Token',
                  hintText: '123456:ABC-DEF...',
                  helperText: 'Create a bot via @BotFather on Telegram',
                  isDense: true,
                ),
                enabled: !connecting,
              ),
              const SizedBox(height: 12),
              Text('Mode',
                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
              const SizedBox(height: 4),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                      value: 'read_only', label: Text('Read-only')),
                  ButtonSegment(
                      value: 'read_write', label: Text('Read & Write')),
                ],
                selected: {selectedMode},
                onSelectionChanged: connecting
                    ? null
                    : (sel) =>
                        setLocalState(() => selectedMode = sel.first),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: connecting || tokenController.text.trim().isEmpty
                    ? null
                    : () async {
                        setLocalState(() => connecting = true);
                        await _connectTelegramBot(
                            tokenController.text.trim(), selectedMode);
                        if (mounted) {
                          setLocalState(() => connecting = false);
                        }
                      },
                child: Text(connecting ? 'Connecting...' : 'Connect Bot'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _telegramBotCard(Map<String, dynamic> bot, ColorScheme cs) {
    final username = bot['bot_username'] as String;
    final mode = bot['mode'] as String;
    final active = bot['active'] as bool;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                InkWell(
                  onTap: () => launchUrl(
                      Uri.parse('https://t.me/$username'),
                      mode: LaunchMode.externalApplication),
                  child: Text('@$username',
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: cs.primary)),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: active
                        ? Colors.green.withValues(alpha: 0.1)
                        : cs.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(active ? 'active' : 'inactive',
                      style: TextStyle(
                          fontSize: 11,
                          color: active
                              ? Colors.green
                              : cs.onSurfaceVariant)),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('Mode',
                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            const SizedBox(height: 4),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'read_only', label: Text('Read-only')),
                ButtonSegment(
                    value: 'read_write', label: Text('Read & Write')),
              ],
              selected: {mode},
              onSelectionChanged: (sel) =>
                  _updateTelegramBotMode(sel.first),
            ),
            const SizedBox(height: 4),
            Text(
              mode == 'read_only'
                  ? 'Bot can answer questions, but it won\'t propose write actions.'
                  : 'Bot can answer questions and propose changes for confirmation.',
              style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            Text('Link a Telegram chat',
                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            const SizedBox(height: 4),
            if (_tgLinkCode != null) ...[
              Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        border: Border.all(color: cs.outlineVariant),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: SelectableText(_tgLinkCode!,
                          style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                              fontFamily: 'monospace')),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.copy, size: 20),
                    onPressed: () {
                      Clipboard.setData(
                          ClipboardData(text: _tgLinkCode!));
                      ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Code copied!')));
                    },
                  ),
                ],
              ),
              if (_tgLinkExpiry > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Send this code in a private chat with your bot. Expires in ${_tgLinkExpiry ~/ 60}:${(_tgLinkExpiry % 60).toString().padLeft(2, '0')}',
                    style: TextStyle(
                        fontSize: 11, color: cs.onSurfaceVariant),
                  ),
                ),
            ] else
              OutlinedButton(
                onPressed: _generateLinkCode,
                child: const Text('Generate Link Code'),
              ),
            const Divider(height: 24),
            TextButton.icon(
              onPressed: _disconnectTelegramBot,
              icon: const Icon(Icons.link_off, size: 16, color: Colors.red),
              label: const Text('Disconnect bot',
                  style: TextStyle(color: Colors.red)),
            ),
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
              if ((s.hasLocation && s.defaultLocation != null) || s.defaultOnlineLink != null) ...[
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
