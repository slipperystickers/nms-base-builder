"""Shared notification state and plain-text replies, compatible with older clients."""
import re
import json
import os

REPLY = re.compile(r'^↪ @([A-Za-z0-9][A-Za-z0-9 _-]{1,23}): ([^\n]{0,160})\n\n([\s\S]*)$')
CHAT_HELP = (
    ('Start chatting', 'Enable Online Access in Blender Preferences, then enable chat. Open chat from the toolbar and choose a conversation. Click a name in the users list to start a direct message.'),
    ('Write a message', 'Type in the message box. Enter sends the message and Shift+Enter starts a new line. The options menu opens account settings and controls where mini chat appears.'),
)
_saved = {}

def load(path):
    try:
        value = json.loads(path.read_text(encoding='utf8')) if path.stat().st_size < 2048000 else {}
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def save(path, state):
    try:
        encoded = json.dumps(state)
        if _saved.get(str(path)) == encoded:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.state-new')
        temporary.write_text(encoded, encoding='utf8')
        os.replace(temporary, path)
        _saved[str(path)] = encoded
    except OSError:
        pass

def reply_parts(text):
    match = REPLY.match(text or '')
    return match.groups() if match else None

def make_reply(name, quote, body):
    return f'↪ @{name}: {" ".join(quote.split())[:120]}\n\n{body}'

def preview(message):
    raw = str(message.get('text', ''))
    reply = reply_parts(raw)
    text = ' '.join((reply[2] if reply else raw).split())
    if text:
        return text
    attachment = message.get('attachment')
    if attachment:
        kind = 'Image' if attachment.get('mime', '').startswith('image/') else 'Video' if attachment.get('mime', '').startswith('video/') else 'File'
        return kind + ' · ' + attachment.get('name', 'attachment')
    return 'New message'

def message_room(message):
    return message.get('from') if message.get('to') else 'main'


def remember_received(state, messages, persona, names):
    """Keep incoming previews separately from unread counts and room selection."""
    own = {n.get('id') for n in names} | {persona}
    state['own_ids'] = sorted(own - {None})
    cache = state.setdefault('content', {})
    rooms = state.setdefault('latest_by_room', {})
    # Seed older saved notification states without waiting for another message.
    candidates = [*cache.values(), *rooms.values(), *messages]
    if state.get('latest'):
        candidates.insert(0, state['latest'])
    for m in candidates:
        if not m.get('id'):
            continue
        merged = {**cache.get(m['id'], {}), **m}
        cache[m['id']] = merged
        if merged.get('from') in own:
            continue
        room = message_room(merged)
        previous = rooms.get(room)
        if previous is None or merged.get('time', 0) > previous.get('time', 0):
            rooms[room] = merged
        elif merged['id'] == previous.get('id'):
            rooms[room] = {**previous, **merged}
        latest = state.get('latest')
        if latest is None or merged.get('time', 0) > latest.get('time', 0):
            state['latest'] = merged
        elif merged['id'] == latest.get('id'):
            state['latest'] = {**latest, **merged}
    state['latest_by_room'] = dict(sorted(
        ((room, m) for room, m in rooms.items() if m.get('from') not in own),
        key=lambda pair: pair[1].get('time', 0))[-200:])
    state['content'] = dict(sorted(cache.items(), key=lambda pair: pair[1].get('time', 0))[-200:])


def latest_received(state, target=None):
    room = target or 'main'
    latest = state.get('latest_by_room', {}).get(room)
    if latest is None:
        # Compatibility with a state saved before per-conversation previews.
        candidates = [*state.get('content', {}).values()]
        if state.get('latest'):
            candidates.append(state['latest'])
        own = set(state.get('own_ids', [])) | {state.get('persona')}
        candidates = [m for m in candidates if message_room(m) == room and m.get('from') not in own]
        latest = max(candidates, key=lambda m: m.get('time', 0), default=None)
    return latest


def _attention_state(state):
    if 'dm_seen' in state:
        return
    # Migrate existing unread DMs; don't revive every old conversation.
    rooms = state.get('latest_by_room', {})
    state['dm_seen'] = {room: m.get('time', 0) for room, m in rooms.items() if room != 'main'}
    state['dm_pending'] = {room: m for room, m in rooms.items()
                           if room != 'main' and state.get('unread', {}).get(room)}
    state['bar_room'] = max(state['dm_pending'],
                            key=lambda room: state['dm_pending'][room].get('time', 0), default=None)


def _receive_attention(state, baseline=False):
    for room, message in sorted(state.get('latest_by_room', {}).items(),
                                key=lambda pair: pair[1].get('time', 0)):
        if room == 'main':
            continue
        timestamp = message.get('time', 0)
        if timestamp > state['dm_seen'].get(room, -1):
            state['dm_seen'][room] = timestamp
            if not baseline:
                state['dm_pending'][room] = message
                state['bar_room'] = room
        elif room in state['dm_pending'] and message.get('id') == state['dm_pending'][room].get('id'):
            state['dm_pending'][room] = message  # Hydrate sparse inbox entries.


def answered(state, target, received):
    """Acknowledge only the response visible when Send was pressed."""
    _attention_state(state)
    pending = state['dm_pending'].get(target)
    if not pending or not received or pending.get('time', 0) > received.get('time', 0):
        return
    state['dm_pending'].pop(target, None)
    if state.get('bar_room') == target:
        state['bar_room'] = min(state['dm_pending'],
                                key=lambda room: state['dm_pending'][room].get('time', 0), default=None)


def mark_read(state, target, received):
    """Stop attention for the incoming message actually displayed to the user.

    Keep the response queue so replying still advances to the next unanswered
    DM. A later message must be allowed to request attention again.
    """
    if not target or target == 'main' or not received:
        return
    read = state.setdefault('dm_read', {})
    read[target] = max(read.get(target, -1), received.get('time', 0))
    latest = latest_received(state, target)
    if latest and latest.get('time', 0) <= read[target]:
        state.get('unread', {}).pop(target, None)
        state.get('directed', {}).pop(target, None)


def bar_message(state):
    _attention_state(state)
    room = state.get('bar_room')
    read = state.get('dm_read', {})
    pending = state['dm_pending'].get(room)
    if pending and pending.get('time', 0) > read.get(room, -1):
        return pending, room
    # A viewed DM can remain in the reply queue, but it no longer owns the
    # toolbar preview. Prefer another DM that still needs attention.
    room = min((key for key, message in state['dm_pending'].items()
                if message.get('time', 0) > read.get(key, -1)),
               key=lambda key: state['dm_pending'][key].get('time', 0), default=None)
    return (state['dm_pending'][room], room) if room else (latest_received(state), None)


def pulse_on(seconds):
    # Slow, theme-native emphasis; no additional network or fast redraw loop.
    return int(seconds) % 2 == 0


def update(state, value, persona, names, viewed=None):
    """Merge sparse notifications without discarding rich message content."""
    if state.get('persona') != persona:
        state.clear()
        state.update(persona=persona, seen=None, unread={}, directed={}, latest=None, content={})
    own = {n.get('id') for n in names} | {persona}
    own_names = {n.get('name','').casefold() for n in names}
    inbox = value.get('inbox', [])
    _attention_state(state)
    baseline = state.get('seen') is None
    remember_received(state, [*inbox, *value.get('messages', [])], persona, names)
    _receive_attention(state, baseline)
    cache = state['content']
    seen = state.get('seen')
    for raw in inbox:
        m = cache.get(raw['id'], raw)
        if m.get('from') in own or seen is None or m['id'] in seen: continue
        room = m['from'] if m.get('to') else 'main'
        if room == viewed: continue
        state['unread'][room] = state['unread'].get(room, 0) + 1
        reply = reply_parts(m.get('text'))
        if m.get('to') == persona or (reply and reply[0].casefold() in own_names):
            state['directed'][room] = state['directed'].get(room, 0) + 1
    state['seen'] = [m['id'] for m in inbox]
    if viewed:
        state['unread'].pop(viewed, None)
        state['directed'].pop(viewed, None)
        displayed = [m for m in value.get('messages', [])
                     if m.get('from') not in own and message_room(m) == viewed]
        mark_read(state, viewed, max(displayed, key=lambda m: m.get('time', 0), default=None))
    state['content'] = dict(sorted(cache.items(), key=lambda pair: pair[1].get('time',0))[-200:])
    return state

def toolbar(state, online, target=None):
    latest, room = bar_message(state)
    read = state.get('dm_read', {})
    unread = sum(m.get('time', 0) > read.get(key, -1)
                 for key, m in state['dm_pending'].items())
    attention = bool(latest and room and latest.get('time', 0) > read.get(room, -1))
    return dict(preview=(f"{latest.get('name', 'User')}: {preview(latest)}" if latest else 'Waiting for messages')[:512],
                unread=unread, directed=unread if attention else 0, online=online, target=room)
