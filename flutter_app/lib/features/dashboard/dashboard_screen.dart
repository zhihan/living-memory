import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/room.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  List<Room>? _rooms;
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
      final rooms = await api.listRooms();
      if (mounted) setState(() => _rooms = rooms);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  static const _timezones = [
    'UTC',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Sao_Paulo',
    'Europe/London',
    'Europe/Berlin',
    'Europe/Moscow',
    'Asia/Tokyo',
    'Asia/Shanghai',
    'Asia/Kolkata',
    'Asia/Taipei',
    'Australia/Sydney',
    'Pacific/Auckland',
  ];

  Future<void> _createRoom() async {
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (ctx) {
        final controller = TextEditingController();
        var selectedTz = 'UTC';
        return StatefulBuilder(
          builder: (ctx, setDialogState) => AlertDialog(
            title: const Text('New Room'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: controller,
                  decoration: const InputDecoration(labelText: 'Title'),
                  autofocus: true,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: selectedTz,
                  decoration: const InputDecoration(labelText: 'Timezone'),
                  items: _timezones
                      .map((tz) => DropdownMenuItem(value: tz, child: Text(tz)))
                      .toList(),
                  onChanged: (v) => setDialogState(() => selectedTz = v!),
                ),
              ],
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
              FilledButton(
                  onPressed: () => Navigator.pop(ctx, {
                    'title': controller.text,
                    'timezone': selectedTz,
                  }),
                  child: const Text('Create')),
            ],
          ),
        );
      },
    );
    if (result == null || result['title']!.trim().isEmpty) return;
    try {
      await context.read<ApiService>().createRoom(
          title: result['title']!.trim(),
          timezone: result['timezone']!);
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
        title: const Text('Rooms'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => context.read<AuthService>().signOut(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _createRoom,
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
    final rooms = _rooms ?? [];
    if (rooms.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.meeting_room_outlined,
                size: 48, color: Theme.of(context).colorScheme.onSurfaceVariant),
            const SizedBox(height: 12),
            Text('No rooms yet',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text('Tap + to create one',
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 80),
        itemCount: rooms.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final room = rooms[index];
          final colors = [
            Colors.indigo,
            Colors.teal,
            Colors.deepOrange,
            Colors.purple,
            Colors.blue,
          ];
          final color = colors[index % colors.length];
          return Card(
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => context.push('/rooms/${room.roomId}'),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    CircleAvatar(
                      backgroundColor: color.withValues(alpha: 0.12),
                      radius: 22,
                      child: Text(
                        room.title.isNotEmpty ? room.title[0].toUpperCase() : '?',
                        style: TextStyle(
                          color: color,
                          fontWeight: FontWeight.w600,
                          fontSize: 18,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Flexible(
                                child: Text(room.title,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600, fontSize: 15),
                                    overflow: TextOverflow.ellipsis),
                              ),
                              if (room.myRole != null && room.myRole != 'organizer') ...[
                                const SizedBox(width: 6),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                                  decoration: BoxDecoration(
                                    color: Theme.of(context).colorScheme.secondaryContainer,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Text(
                                    room.myRole!,
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.w500,
                                      color: Theme.of(context).colorScheme.onSecondaryContainer,
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          const SizedBox(height: 2),
                          Text(room.seriesSubtitle,
                              style: TextStyle(
                                  fontSize: 12,
                                  color: Theme.of(context).colorScheme.onSurfaceVariant)),
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right,
                        color: Theme.of(context).colorScheme.onSurfaceVariant),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
