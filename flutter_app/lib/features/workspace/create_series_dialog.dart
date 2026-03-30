import 'package:flutter/material.dart';

class CreateSeriesDialog extends StatefulWidget {
  const CreateSeriesDialog({super.key});

  @override
  State<CreateSeriesDialog> createState() => _CreateSeriesDialogState();
}

class _CreateSeriesDialogState extends State<CreateSeriesDialog> {
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _timeController = TextEditingController();
  final _durationController = TextEditingController(text: '60');
  final _locationController = TextEditingController();
  final _linkController = TextEditingController();

  String _kind = 'meeting';
  String _frequency = 'weekly';
  final Set<int> _weekdays = {1}; // Monday default
  String _locationType = 'fixed';
  final List<int> _checkInWeekdays = [];

  static const _weekdayLabels = {
    1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu',
    5: 'Fri', 6: 'Sat', 7: 'Sun',
  };

  void _submit() {
    if (_titleController.text.trim().isEmpty) return;
    final body = <String, dynamic>{
      'kind': _kind,
      'title': _titleController.text.trim(),
      'schedule_rule': {
        'frequency': _frequency,
        'weekdays': _weekdays.toList()..sort(),
        'interval': 1,
      },
      if (_timeController.text.isNotEmpty) 'default_time': _timeController.text,
      if (_durationController.text.isNotEmpty)
        'default_duration_minutes': int.tryParse(_durationController.text),
      if (_locationController.text.isNotEmpty)
        'default_location': _locationController.text,
      if (_linkController.text.isNotEmpty)
        'default_online_link': _linkController.text,
      'location_type': _locationType,
      if (_descriptionController.text.isNotEmpty)
        'description': _descriptionController.text,
      if (_checkInWeekdays.isNotEmpty) 'check_in_weekdays': _checkInWeekdays,
    };
    Navigator.pop(context, body);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New Series'),
      content: SizedBox(
        width: double.maxFinite,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _titleController,
                decoration: const InputDecoration(labelText: 'Title'),
                autofocus: true,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _descriptionController,
                decoration: const InputDecoration(labelText: 'Description'),
                maxLines: 2,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Kind'),
                items: const [
                  DropdownMenuItem(value: 'meeting', child: Text('Meeting')),
                  DropdownMenuItem(value: 'reminder', child: Text('Reminder')),
                  DropdownMenuItem(value: 'study_assignment', child: Text('Study')),
                ],
                onChanged: (v) => setState(() => _kind = v!),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _frequency,
                decoration: const InputDecoration(labelText: 'Frequency'),
                items: const [
                  DropdownMenuItem(value: 'daily', child: Text('Daily')),
                  DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                  DropdownMenuItem(value: 'weekdays', child: Text('Weekdays')),
                  DropdownMenuItem(value: 'once', child: Text('One-time')),
                ],
                onChanged: (v) => setState(() => _frequency = v!),
              ),
              if (_frequency == 'weekly') ...[
                const SizedBox(height: 12),
                const Text('Weekdays'),
                Wrap(
                  spacing: 4,
                  children: _weekdayLabels.entries.map((e) {
                    return FilterChip(
                      label: Text(e.value),
                      selected: _weekdays.contains(e.key),
                      onSelected: (sel) {
                        setState(() {
                          if (sel) {
                            _weekdays.add(e.key);
                          } else {
                            _weekdays.remove(e.key);
                          }
                        });
                      },
                    );
                  }).toList(),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: _timeController,
                decoration:
                    const InputDecoration(labelText: 'Time (HH:MM)', hintText: '09:00'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _durationController,
                decoration:
                    const InputDecoration(labelText: 'Duration (min)'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _locationType,
                decoration: const InputDecoration(labelText: 'Location Type'),
                items: const [
                  DropdownMenuItem(value: 'fixed', child: Text('Fixed')),
                  DropdownMenuItem(value: 'per_occurrence', child: Text('Per Occurrence')),
                  DropdownMenuItem(value: 'rotation', child: Text('Rotation')),
                ],
                onChanged: (v) => setState(() => _locationType = v!),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _locationController,
                decoration: const InputDecoration(labelText: 'Location'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _linkController,
                decoration:
                    const InputDecoration(labelText: 'Online Link'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Create')),
      ],
    );
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _timeController.dispose();
    _durationController.dispose();
    _locationController.dispose();
    _linkController.dispose();
    super.dispose();
  }
}
