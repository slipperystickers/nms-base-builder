"""Native buildable knowledge plans and guarded, explicit save publication.

Knowledge changes are additive; currency changes are explicit. Inventories and
progress are preserved. Every save point is edited from its own original.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

RESOURCES = Path(__file__).parents[1] / 'resources'
KEYS = json.loads((RESOURCES / 'ship_management_keys.json').read_text(encoding='utf-8'))
SAVE_FIELDS = frozenset(('KnownProducts', 'KnownTech', 'KnownSpecials'))
ACCOUNT_FIELDS = frozenset(('UnlockedSeasonRewards', 'UnlockedSpecials', 'UnlockedTwitchRewards', 'UnlockedPlatformRewards', 'UnlockedTitles'))
CURRENCY_FIELDS = {'Units': 'Units', 'Nanites': 'Nanites', 'Quicksilver': 'Specials'}
CURRENCY_MAX = 0xffffffff
# Primary NMSE Core/MainStatsLogic.cs: StatFields and WriteStatValues treat all
# three currencies as uint32, serialized through unchecked((int)(uint)value).
# Large balances can therefore appear as signed negative integers in JSON.
CATALOGUE = RESOURCES / 'buildable_unlocks.json'
SAVE_NAME = re.compile(r'save(\d*)\.hg$', re.I)


def key(obj, name):
    encoded = KEYS.get(name, name)
    if name != encoded and name in obj and encoded in obj:
        raise ValueError(f'Ambiguous translated save field: {name}')
    return name if name in obj else encoded


def get(obj, name, default=None):
    return obj.get(key(obj, name), default) if isinstance(obj, dict) else default


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _update(progress, fraction, detail):
    if progress is not None:
        progress.update(fraction, detail)


def item_key(item):
    return f"{item['kind']}:{item['id']}"


def load_catalogue(path=None):
    data = json.loads(Path(path or CATALOGUE).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('items'), list):
        raise ValueError('Unsupported buildable item catalogue')
    seen = set()
    for item in data['items']:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ('id', 'name', 'kind', 'category')):
            raise ValueError('Incomplete buildable catalogue item')
        if item['id'].startswith('^') or any(c.isspace() for c in item['id']):
            raise ValueError('Invalid native catalogue ID')
        identity = item_key(item)
        if identity in seen:
            raise ValueError(f'Duplicate buildable catalogue item: {identity}')
        seen.add(identity)
        if item.get('unlock_field') not in SAVE_FIELDS | {'AccountWideSpecials', None}:
            raise ValueError(f'Unsupported unlock operation for {identity}')
        if item.get('account_field') not in ACCOUNT_FIELDS | {None}:
            raise ValueError(f'Unsupported account reward field for {identity}')
        if not isinstance(item.get('extra_save_fields', []), list) or any(field not in SAVE_FIELDS for field in item.get('extra_save_fields', [])):
            raise ValueError(f'Unsupported additional save fields for {identity}')
    return data


def player(root, context):
    if context not in ('Main', 'Season'):
        raise ValueError('Choose Main or Expedition')
    container = get(root, 'BaseContext' if context == 'Main' else 'ExpeditionContext')
    # Old save versions store the one player context directly at root.
    if container is None and context == 'Main':
        container = root
    state = get(container, 'PlayerStateData')
    if not isinstance(state, dict):
        raise ValueError(f'{context} player data is unavailable in this save point')
    return state


def contexts(root):
    available = []
    for context in ('Main', 'Season'):
        try:
            player(root, context)
            available.append(context)
        except ValueError:
            pass
    return available


def common_contexts(roots):
    if not roots:
        return []
    return [c for c in ('Main', 'Season') if all(c in contexts(root) for root in roots.values())]


def knowledge(root, context, field):
    if field not in SAVE_FIELDS:
        raise ValueError('This operation does not edit a per-save knowledge list')
    state = player(root, context)
    values = get(state, field)
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError(f'{field} is missing or has an unsupported format')
    return values


def currency_value(root, context, name):
    """Read a supported currency as an unsigned amount without changing JSON."""
    if name not in CURRENCY_FIELDS:
        raise ValueError(f'Unsupported currency: {name}')
    value = get(player(root, context), CURRENCY_FIELDS[name])
    if type(value) is not int or not -(1 << 31) <= value <= CURRENCY_MAX:
        raise ValueError(f'{name} is missing or has an unsupported integer format')
    return value & CURRENCY_MAX


def describe_currencies(roots, context):
    """Return per-point values, differences and availability for currency UI."""
    result = {}
    for name, field in CURRENCY_FIELDS.items():
        values, reason = {}, ''
        try:
            if not roots:
                raise ValueError('No save points selected')
            values = {str(path): currency_value(root, context, name) for path, root in roots.items()}
        except ValueError as exc:
            reason = str(exc)
        result[name] = dict(field=field, minimum=0, maximum=CURRENCY_MAX,
                            values=values, value=next(iter(values.values()), None),
                            mixed=len(set(values.values())) > 1,
                            supported=not reason, unavailable_reason=reason, reason=reason)
    return result


def _currency_edits(currencies):
    if currencies is None:
        return {}
    if not isinstance(currencies, dict):
        raise ValueError('Currency changes must be a dictionary of integer amounts')
    result = {}
    for name, value in currencies.items():
        if name not in CURRENCY_FIELDS:
            raise ValueError(f'Unsupported currency: {name}')
        if type(value) is not int or not 0 <= value <= CURRENCY_MAX:
            raise ValueError(f'{name} must be a whole number from 0 to {CURRENCY_MAX:,}')
        result[name] = value
    return result


def account_knowledge(root, field):
    if field not in ACCOUNT_FIELDS:
        raise ValueError('No verified account reward field for this item')
    settings = get(root, 'UserSettingsData')
    values = get(settings, field)
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError(f'Account {field} is missing or unsupported')
    return values


def item_save_fields(item):
    primary = item.get('unlock_field')
    return list(dict.fromkeys(([primary] if primary in SAVE_FIELDS else []) + item.get('extra_save_fields', [])))


def describe_items(roots, context, catalogue, account_root=None, progress=None):
    """All catalogue rows, including unavailable scopes, for a checkbox UI."""
    _update(progress, 0., 'Reading existing construction and technology knowledge')
    saved, rewards = {}, {}
    for field in SAVE_FIELDS:
        try:
            if not roots:
                raise ValueError('No save points selected')
            saved[field] = [{v.lstrip('^') for v in knowledge(root, context, field)} for root in roots.values()]
        except ValueError as exc:
            saved[field] = str(exc)
    for field in ACCOUNT_FIELDS:
        try:
            if account_root is None:
                raise ValueError('Verified account reward data is unavailable')
            rewards[field] = {v.lstrip('^') for v in account_knowledge(account_root, field)}
        except ValueError as exc:
            rewards[field] = str(exc)
    result = []
    total = len(catalogue['items'])
    for index, item in enumerate(catalogue['items']):
        if index % 200 == 0:
            _update(progress, .1 + .9 * index / max(1, total), f'Checking item availability: {index:,} / {total:,}')
        row = dict(item, key=item_key(item), known_count=0, point_count=len(roots), account_known=False)
        field = item.get('unlock_field')
        reason = ''
        if field in SAVE_FIELDS:
            try:
                fields = item_save_fields(item)
                for name in fields:
                    if isinstance(saved[name], str):
                        raise ValueError(saved[name])
                row['known_count'] = sum(all(item['id'] in saved[name][point] for name in fields) for point in range(len(roots)))
            except ValueError as exc:
                reason = str(exc)
        elif field == 'AccountWideSpecials':
            row['point_count'] = 1
        else:
            reason = item.get('scope_note') or 'No verified save unlock mapping for this native item'
        if item.get('account_field') or field == 'AccountWideSpecials':
            try:
                if not item.get('account_id'):
                    raise ValueError('No verified native account reward ID')
                known = rewards.get(item.get('account_field'), 'No verified account reward field for this item')
                if isinstance(known, str):
                    raise ValueError(known)
                row['account_known'] = item['account_id'].lstrip('^') in known
                if field == 'AccountWideSpecials':
                    row['known_count'] = int(row['account_known'])
            except ValueError as exc:
                reason = str(exc)
        row['supported'] = not reason
        row['unavailable_reason'] = reason
        row['already_known'] = row['supported'] and row['known_count'] == row['point_count'] and (
            not item.get('account_field') or row['account_known'])
        result.append(row)
    _update(progress, 1., f'Checked {total:,} native catalogue items')
    return result


def make_plan(roots, context, selected, catalogue, account_root=None, currencies=None, progress=None):
    """Return independent drafts; never mutate inputs or remove learned IDs."""
    _update(progress, 0., 'Checking the selected items and currency amounts')
    selected = list(dict.fromkeys(selected))
    currencies = _currency_edits(currencies)
    if not selected and not currencies:
        raise ValueError('Select an item to unlock or edit a currency')
    if context not in common_contexts(roots):
        raise ValueError('This context is not present in every selected save point')
    _update(progress, .15, 'Checking item and reward availability')
    rows = {r['key']: r for r in describe_items(roots, context, catalogue, account_root)} if selected else {}
    unknown = [identity for identity in selected if identity not in rows]
    if unknown:
        raise ValueError('Item is absent from the installed native catalogue: ' + ', '.join(unknown))
    unavailable = [rows[identity] for identity in selected if not rows[identity]['supported']]
    if unavailable:
        raise ValueError('; '.join(r['name'] + ': ' + r['unavailable_reason'] for r in unavailable[:5]))
    _update(progress, .35, 'Preparing independent save-point changes')
    drafts = copy.deepcopy(roots)
    account_draft = copy.deepcopy(account_root)
    changes = []
    currency_changes = []
    for index, (path, draft) in enumerate(drafts.items()):
        _update(progress, .45 + .35 * index / max(1, len(drafts)), f'Preparing {Path(path).name}')
        for name, amount in currencies.items():
            previous = currency_value(draft, context, name)
            if previous != amount:
                state = player(draft, context)
                field = CURRENCY_FIELDS[name]
                stored = amount if amount <= 0x7fffffff else amount - (1 << 32)
                state[key(state, field)] = stored
                currency_changes.append(dict(path=str(path), context=context, currency=name,
                                             field=field, before=previous, after=amount))
        for field in sorted(SAVE_FIELDS):
            chosen = [rows[identity]['id'] for identity in selected if field in item_save_fields(rows[identity])]
            if not chosen:
                continue
            values = knowledge(draft, context, field)
            known = {v.lstrip('^') for v in values}
            added = ['^' + identifier for identifier in chosen if identifier not in known]
            # Product and technology IDs are unique within their own field.
            added = list(dict.fromkeys(added))
            if added:
                values.extend(added)
                changes.append(dict(path=str(path), context=context, field=field, added=added))
    _update(progress, .8, 'Preparing account reward changes')
    account_changes = []
    for field in sorted(ACCOUNT_FIELDS):
        chosen = [rows[identity].get('account_id') for identity in selected if rows[identity].get('account_field') == field]
        if not chosen:
            continue
        values = account_knowledge(account_draft, field)
        known = {v.lstrip('^') for v in values}
        added = list(dict.fromkeys('^' + identifier.lstrip('^') for identifier in chosen if identifier.lstrip('^') not in known))
        if added:
            values.extend(added)
            account_changes.append(dict(field=field, added=added))
    _update(progress, .9, 'Verifying the reviewed source fingerprints')
    result = dict(context=context, selected=selected, original_fingerprints={str(p): fingerprint(r) for p, r in roots.items()},
                roots=drafts, changes=changes, item_count=len(selected),
                addition_count=sum(len(c['added']) for c in changes) + sum(len(c['added']) for c in account_changes),
                account_root=account_draft, account_changes=account_changes,
                currencies=currencies, currency_changes=currency_changes,
                original_account_fingerprint=fingerprint(account_root) if account_root is not None else None,
                account_changed=bool(account_changes))
    _update(progress, 1., 'Unlock and currency changes prepared')
    return result


def validate_plan(originals, plan, catalogue, account_root=None):
    if {str(p): fingerprint(r) for p, r in originals.items()} != plan['original_fingerprints']:
        raise ValueError('The reviewed source data changed')
    if (fingerprint(account_root) if account_root is not None else None) != plan['original_account_fingerprint']:
        raise ValueError('The reviewed account reward data changed')
    expected = make_plan(originals, plan['context'], plan['selected'], catalogue, account_root,
                         currencies=plan.get('currencies'))
    if expected != plan:
        raise ValueError('Unlock draft includes changes outside the reviewed item selection')


def _save_paths(paths):
    paths = list(dict.fromkeys(Path(p).resolve() for p in paths))
    slots = set()
    if not paths or len(paths) > 2 or len({p.parent for p in paths}) != 1:
        raise ValueError('Choose one save slot with one or two save points')
    for path in paths:
        match = SAVE_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise ValueError(f'Unsupported or missing save point: {path.name}')
        number = int(match.group(1) or '1')
        if not 1 <= number <= 30:
            raise ValueError('Unsupported save slot number')
        slots.add((number + 1) // 2)
    if len(slots) != 1:
        raise ValueError('The selected files belong to different save slots')
    return paths


def read_review(paths, progress=None):
    """Stable read of each save point and its optional Steam metadata."""
    from .save_file import SaveFile
    from . import ship_files
    _update(progress, 0., 'Checking the selected save points')
    paths = _save_paths(paths)
    latest_path = str(max(paths, key=lambda path: (path.stat().st_mtime_ns, str(path))))
    metadata = {str(p.with_name('mf_' + p.name)): p.with_name('mf_' + p.name).exists() for p in paths}
    _update(progress, .08, 'Hashing save data and companion metadata')
    expected = ship_files.export_hashes(paths)
    roots = {}
    for index, path in enumerate(paths):
        _update(progress, .15 + .35 * index / len(paths), f'Loading {path.name}')
        roots[str(path)] = SaveFile(path).load()
    _update(progress, .55, 'Verifying the source files stayed unchanged')
    if expected != ship_files.export_hashes(paths) or any(Path(p).exists() != exists for p, exists in metadata.items()):
        raise ValueError('Save files changed while opening the unlock review; reopen it')
    available = common_contexts(roots)
    if not available:
        raise ValueError('No common supported player context in the selected save points')
    from . import account_unlock_files
    account = None
    account_error = ''
    _update(progress, .7, 'Reading account reward availability')
    try:
        account = account_unlock_files.read_account(paths[0].parent)
        expected.update(account['hashes'])
    except (ValueError, OSError) as exc:
        account_error = str(exc)
    _update(progress, .85, 'Loading the native buildable item catalogue')
    catalogue = load_catalogue()
    result = dict(paths=[str(p) for p in paths], latest_path=latest_path, roots=roots, hashes=expected, metadata_exists=metadata,
                  contexts=available, catalogue=catalogue, account=account, account_error=account_error)
    _update(progress, 1., 'Save points and account rewards reviewed')
    return result


def apply_review(review, plan, progress=None):
    """Explicit Apply only: validate, back up, stage and atomically publish."""
    from . import ship_files
    _update(progress, 0., 'Validating the reviewed unlock and currency changes')
    account = review.get('account')
    validate_plan(review['roots'], plan, review['catalogue'], account['root'] if account else None)
    if not plan['changes'] and not plan['account_changed'] and not plan['currency_changes']:
        raise ValueError('No changes: selected items are already learned and currency balances are unchanged')
    if any(Path(p).exists() != exists for p, exists in review['metadata_exists'].items()):
        raise ValueError('Save metadata changed since review; reopen the unlock panel')
    _update(progress, .2, 'Preparing verified backups and save publication')
    commit_progress = None
    if progress is not None:
        from .. import progress_ui
        commit_progress = progress_ui.Range(progress, .2, 1.)
    # commit_roots checks all reviewed hashes before staging and again before
    # publication, verifies compressed readback, and backs up data + metadata.
    changed = {path: root for path, root in plan['roots'].items() if root != review['roots'][path]}
    if plan['account_changed']:
        from . import account_unlock_files
        return account_unlock_files.commit_bundle(changed, account, plan['account_root'], review['hashes'], progress=commit_progress)
    return ship_files.commit_roots(changed, review['hashes'], progress=commit_progress)
