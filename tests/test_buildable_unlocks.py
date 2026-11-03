"""Unlock drafts and publication operate on disposable fixtures only."""
import copy
import importlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ADDON = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder'
PACKAGE = '_unlock_test_addon'
package = types.ModuleType(PACKAGE); package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
editor = types.ModuleType(PACKAGE + '.save_editor'); editor.__path__ = [str(ADDON / 'save_editor')]
sys.modules[editor.__name__] = editor
core = importlib.import_module(editor.__name__ + '.buildable_unlocks')

CATALOGUE = dict(schema_version=1, items=[
    dict(id='BUILDWALL', name='Metal Wall', kind='Product', category='Construction', object_ids=['BUILDWALL'], unlock_field='KnownProducts'),
    dict(id='HYPERDRIVE', name='Hyperdrive', kind='Technology', category='Starship Technology', object_ids=[], unlock_field='KnownTech'),
    dict(id='EXCLUSIVE', name='Unmapped reward', kind='Product', category='Expedition', object_ids=[], unlock_field=None, scope_note='Account entitlement mapping unavailable'),
])


def fixture(index=1):
    return dict(BaseContext=dict(PlayerStateData=dict(KnownProducts=['^EXISTING', '^EXISTING'], KnownTech=[],
                Inventory={'Keep': index}, KnownSpecials=['^ACCOUNT_KEEP'], Units=1000 * index, Nanites=100 * index, Specials=10 * index)),
                ExpeditionContext=dict(PlayerStateData=dict(KnownProducts=['^SEASON_KEEP'], KnownTech=['^SEASON_TECH'],
                    Units=10000 * index, Nanites=1000 * index, Specials=100 * index)),
                CommonStateData=dict(SaveName=f'Fixture {index}', SaveUniversalId='0x123456789ABCDEF0'),
                Unknown={'Seed': 2**63 + index, 'Text': '星🚀', 'Data': [1.25, -9, None]},
                UserSettingsData=dict(UnlockedSeasonRewards=['^REWARD_KEEP'], UnlockedSpecials=['^SPECIAL_KEEP']))


def obfuscate(value):
    if isinstance(value, dict):
        return {core.KEYS.get(k, k): obfuscate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [obfuscate(v) for v in value]
    return value


class DraftTests(unittest.TestCase):
    def test_expanded_native_rewards_and_terminal_scope(self):
        catalogue = core.load_catalogue()
        coverage = catalogue['coverage']
        self.assertEqual((coverage['covered_object_count'], coverage['native_object_count']), (2340, 2340))
        self.assertEqual((coverage['covered_season_rewards'], coverage['native_season_rewards']), (293, 293))
        self.assertEqual((coverage['covered_twitch_rewards'], coverage['native_twitch_rewards']), (435, 435))
        self.assertEqual((coverage['covered_platform_rewards'], coverage['native_platform_rewards']), (3, 3))
        self.assertEqual((coverage['covered_titles'], coverage['native_titles']), (346, 346))
        self.assertEqual(sum('Twitch reward' in item.get('tags', []) for item in catalogue['items']), 435)
        by_key = {core.item_key(item): item for item in catalogue['items']}
        for identifier in ('NPCBUILDERTERM', 'NPCVEHICLETERM'):
            self.assertEqual(by_key['Product:' + identifier]['unlock_field'], 'KnownProducts')
        season = by_key['Product:EXPD_EGG_23']
        self.assertEqual((season['account_field'], season['account_id']),
                         ('UnlockedSeasonRewards', 'EXPD_EGG_23'))
        self.assertEqual((by_key['Title:T_EXPD14']['account_field'], by_key['Title:T_EXPD14']['related_id']),
                         ('UnlockedTitles', 'EXPD_TITLE14'))
        twitch = next(item for item in catalogue['items'] if item['kind'] == 'Twitch Reward')
        platform = next(item for item in catalogue['items'] if item['kind'] == 'Platform Reward')
        self.assertTrue(twitch['related_id'] and platform['related_id'])
        roots = {'save9.hg': fixture()}
        account = {'UserSettingsData': {field: [] for field in core.ACCOUNT_FIELDS},
                   'Unrelated': {'Preserve': True}}
        selected = ['Product:NPCBUILDERTERM', 'Product:NPCVEHICLETERM',
                    'Product:EXPD_EGG_23', 'Title:T_EXPD14', core.item_key(twitch), core.item_key(platform)]
        plan = core.make_plan(roots, 'Main', selected, catalogue, account)
        core.validate_plan(roots, plan, catalogue, account)
        self.assertEqual(plan['account_root']['Unrelated'], account['Unrelated'])
        self.assertEqual(plan['account_root']['UserSettingsData']['UnlockedSeasonRewards'], ['^EXPD_EGG_23'])
        self.assertEqual(plan['account_root']['UserSettingsData']['UnlockedTwitchRewards'], ['^' + twitch['id']])
        self.assertEqual(plan['account_root']['UserSettingsData']['UnlockedPlatformRewards'], ['^' + platform['id']])
        self.assertEqual(plan['account_root']['UserSettingsData']['UnlockedTitles'], ['^T_EXPD14'])
        self.assertEqual(roots['save9.hg'], fixture())
        self.assertTrue({'^NPCBUILDERTERM', '^NPCVEHICLETERM'} <=
                        set(core.knowledge(plan['roots']['save9.hg'], 'Main', 'KnownProducts')))

    def test_currency_only_plan_preserves_unedited_balances_and_contexts(self):
        roots = {'save9.hg': fixture(1), 'save10.hg': obfuscate(fixture(2))}
        before = copy.deepcopy(roots)
        info = core.describe_currencies(roots, 'Main')
        self.assertEqual(info['Units']['values'], {'save9.hg': 1000, 'save10.hg': 2000})
        self.assertTrue(info['Units']['mixed'])
        plan = core.make_plan(roots, 'Main', [], CATALOGUE, currencies={'Units': 1000})
        core.validate_plan(roots, plan, CATALOGUE)
        self.assertEqual(plan['item_count'], 0)
        self.assertEqual(plan['changes'], [])
        self.assertEqual(len(plan['currency_changes']), 1)
        self.assertEqual(plan['roots']['save9.hg'], roots['save9.hg'])
        for path, root in plan['roots'].items():
            self.assertEqual(core.currency_value(root, 'Main', 'Units'), 1000)
            for name in ('Nanites', 'Quicksilver'):
                self.assertEqual(core.currency_value(root, 'Main', name), core.currency_value(roots[path], 'Main', name))
            self.assertEqual(core.get(root, 'ExpeditionContext'), core.get(roots[path], 'ExpeditionContext'))
            self.assertEqual(core.knowledge(root, 'Main', 'KnownProducts'), core.knowledge(roots[path], 'Main', 'KnownProducts'))
        self.assertEqual(roots, before)

    def test_full_uint32_currency_boundaries_and_signed_storage(self):
        for name in core.CURRENCY_FIELDS:
            for amount in (0, (1 << 31) - 1, 1 << 31, core.CURRENCY_MAX):
                with self.subTest(currency=name, amount=amount):
                    roots = {'save9.hg': fixture(), 'save10.hg': obfuscate(fixture(2))}
                    plan = core.make_plan(roots, 'Season', [], CATALOGUE, currencies={name: amount})
                    core.validate_plan(roots, plan, CATALOGUE)
                    for path, root in plan['roots'].items():
                        self.assertEqual(core.currency_value(root, 'Season', name), amount)
                        expected_raw = amount if amount < 1 << 31 else amount - (1 << 32)
                        self.assertEqual(core.get(core.player(root, 'Season'), core.CURRENCY_FIELDS[name]), expected_raw)
                        self.assertEqual(core.get(root, 'BaseContext'), core.get(roots[path], 'BaseContext'))
        # Equivalent unsigned and signed JSON spellings remain exact when an
        # explicitly chosen logical amount already matches that save point.
        roots = {'save9.hg': fixture(), 'save10.hg': fixture(2)}
        roots['save9.hg']['BaseContext']['PlayerStateData']['Units'] = -1
        roots['save10.hg']['BaseContext']['PlayerStateData']['Units'] = core.CURRENCY_MAX
        plan = core.make_plan(roots, 'Main', [], CATALOGUE, currencies={'Units': core.CURRENCY_MAX})
        self.assertEqual(plan['roots'], roots)
        self.assertEqual(plan['currency_changes'], [])

    def test_currency_validation_missing_fields_and_tamper_rejection(self):
        roots = {'save9.hg': fixture()}
        for currencies in ([], {'Cash': 1}, {'Units': True}, {'Units': 1.5}, {'Units': '123'},
                           {'Units': -1}, {'Units': core.CURRENCY_MAX + 1}):
            with self.subTest(currencies=currencies), self.assertRaises(ValueError):
                core.make_plan(roots, 'Main', [], CATALOGUE, currencies=currencies)
        root = fixture(); del root['BaseContext']['PlayerStateData']['Specials']
        self.assertFalse(core.describe_currencies({'save9.hg': root}, 'Main')['Quicksilver']['supported'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            core.make_plan({'save9.hg': root}, 'Main', [], CATALOGUE, currencies={'Quicksilver': 50})
        # Unsupported unedited balances never block an otherwise valid unlock.
        root['BaseContext']['PlayerStateData']['Units'] = 1 << 40
        plan = core.make_plan({'save9.hg': root}, 'Main', ['Product:BUILDWALL'], CATALOGUE)
        self.assertEqual(plan['roots']['save9.hg']['BaseContext']['PlayerStateData']['Units'], 1 << 40)
        plan = core.make_plan(roots, 'Main', [], CATALOGUE, currencies={'Units': 500})
        bad = copy.deepcopy(plan); bad['roots']['save9.hg']['BaseContext']['PlayerStateData']['Nanites'] = 999
        with self.assertRaisesRegex(ValueError, 'outside'):
            core.validate_plan(roots, bad, CATALOGUE)
        bad = copy.deepcopy(plan); bad['currencies']['Units'] = 501
        with self.assertRaisesRegex(ValueError, 'outside'):
            core.validate_plan(roots, bad, CATALOGUE)

    def test_complete_native_catalogue_plan_uses_only_declared_fields(self):
        catalogue = core.load_catalogue()
        roots = {'save9.hg': fixture(1), 'save10.hg': obfuscate(fixture(2))}
        account = {'UserSettingsData': {field: ['^PRESERVE_UNKNOWN_REWARD'] for field in core.ACCOUNT_FIELDS}, 'Other': {'Keep': 99}}
        rows = core.describe_items(roots, 'Main', catalogue, account)
        selected = [row['key'] for row in rows if row['supported']]
        self.assertEqual(len(selected), catalogue['coverage']['learnable_count'])
        self.assertEqual(len({i for row in rows for i in row.get('object_ids', [])}), catalogue['coverage']['native_object_count'])
        plan = core.make_plan(roots, 'Main', selected, catalogue, account)
        core.validate_plan(roots, plan, catalogue, account)
        for field in core.SAVE_FIELDS:
            expected = {'^' + row['id'] for row in rows if row['supported'] and field in core.item_save_fields(row)}
            for path in roots:
                actual = set(core.knowledge(plan['roots'][path], 'Main', field)) - set(core.knowledge(roots[path], 'Main', field))
                self.assertEqual(actual, expected - set(core.knowledge(roots[path], 'Main', field)))
        self.assertEqual(plan['account_root']['Other'], account['Other'])
        for field in core.ACCOUNT_FIELDS:
            expected = {'^' + row['account_id'].lstrip('^') for row in rows if row['supported'] and row.get('account_field') == field}
            self.assertEqual(set(core.account_knowledge(plan['account_root'], field)), expected | {'^PRESERVE_UNKNOWN_REWARD'})

    def test_additive_independent_points_and_unknown_fields(self):
        for encoded in (False, True):
            roots = {'save9.hg': fixture(1), 'save10.hg': fixture(2)}
            if encoded:
                roots = {p: obfuscate(r) for p, r in roots.items()}
            before = copy.deepcopy(roots)
            plan = core.make_plan(roots, 'Main', ['Product:BUILDWALL', 'Technology:HYPERDRIVE'], CATALOGUE)
            core.validate_plan(roots, plan, CATALOGUE)
            self.assertEqual(roots, before)
            self.assertEqual(plan['addition_count'], 4)
            for path, root in plan['roots'].items():
                self.assertEqual(core.knowledge(root, 'Main', 'KnownProducts'), ['^EXISTING', '^EXISTING', '^BUILDWALL'])
                self.assertEqual(core.knowledge(root, 'Main', 'KnownTech'), ['^HYPERDRIVE'])
                self.assertEqual(core.get(root, 'ExpeditionContext'), core.get(roots[path], 'ExpeditionContext'))
                self.assertEqual(root['Unknown'], roots[path]['Unknown'])
                self.assertEqual(core.get(root, 'UserSettingsData'), core.get(roots[path], 'UserSettingsData'))
            again = core.make_plan(plan['roots'], 'Main', plan['selected'], CATALOGUE)
            self.assertEqual(again['changes'], [])

    def test_reject_unreviewed_or_unavailable_mutations(self):
        roots = {'save9.hg': fixture()}
        for selection in ([], ['Product:ABSENT'], ['Product:EXCLUSIVE']):
            with self.assertRaises(ValueError):
                core.make_plan(roots, 'Main', selection, CATALOGUE)
        plan = core.make_plan(roots, 'Main', ['Product:BUILDWALL'], CATALOGUE)
        bad = copy.deepcopy(plan); bad['roots']['save9.hg']['Unknown']['Text'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'outside'):
            core.validate_plan(roots, bad, CATALOGUE)
        changed = copy.deepcopy(roots); changed['save9.hg']['Unknown']['Seed'] += 1
        with self.assertRaisesRegex(ValueError, 'source data changed'):
            core.validate_plan(changed, plan, CATALOGUE)

    def test_missing_fields_context_and_ambiguous_keys_fail_closed(self):
        root = fixture(); del root['BaseContext']['PlayerStateData']['KnownProducts']
        rows = core.describe_items({'save.hg': root}, 'Main', CATALOGUE)
        self.assertFalse(rows[0]['supported'])
        with self.assertRaises(ValueError):
            core.make_plan({'save.hg': root}, 'Main', ['Product:BUILDWALL'], CATALOGUE)
        root = fixture(); root['BaseContext'][core.KEYS['PlayerStateData']] = root['BaseContext']['PlayerStateData']
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            core.player(root, 'Main')

    def test_existing_unprefixed_id_not_duplicated(self):
        root = fixture(); root['BaseContext']['PlayerStateData']['KnownProducts'] += ['BUILDWALL']
        plan = core.make_plan({'save.hg': root}, 'Main', ['Product:BUILDWALL'], CATALOGUE)
        self.assertEqual(plan['changes'], [])


def files_module():
    # Isolate Blender-only UI imports; exercise real HG codec, metadata,
    # transactional publication and backup policy on temporary files.
    progress = types.ModuleType(PACKAGE + '.progress_ui')
    class Activity:
        def __init__(self, *args): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def update(self, *args): pass
    class Range:
        def __init__(self, parent, start, end): self.parent, self.start, self.end = parent, start, end
        def update(self, fraction, detail=None): self.parent.update(self.start + (self.end - self.start) * fraction, detail)
    progress.Activity = Activity; progress.Range = Range; sys.modules[progress.__name__] = progress
    utilities = types.ModuleType(editor.__name__ + '.save_editor_utils')
    utilities.BaseType = types.SimpleNamespace(CORVETTE='PlayerShipBase')
    utilities.BaseData = object; utilities.ShowMessageBox = lambda *a, **k: None
    sys.modules[utilities.__name__] = utilities
    translation = types.ModuleType(editor.__name__ + '.save_translation')
    translation.SaveTranslation = type('SaveTranslation', (), {})
    translation.translate_to_obf_data = lambda value: value
    sys.modules[translation.__name__] = translation
    return importlib.import_module(editor.__name__ + '.ship_files')


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.files = files_module()

    def make_files(self, directory):
        paths = [directory / 'save9.hg', directory / 'save10.hg']
        for i, path in enumerate(paths):
            save = self.files.SaveFile(path); save.json_data = fixture(i + 1); save.save()
            plain = bytearray(432); struct.pack_into('<I', plain, 0, 0xeeeeeebe)
            struct.pack_into('<Q', plain, 348, 0x123456789ABCDEF0)
            meta = path.with_name('mf_' + path.name)
            meta.write_bytes(self.files.steam_metadata.crypt(plain, self.files.steam_metadata.storage_number(meta.name)))
        return paths

    def test_commit_keeps_each_point_and_verifies_backups(self):
        with tempfile.TemporaryDirectory(prefix='bbe-unlock-fixture-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory)
            original = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
            with patch.object(core, 'load_catalogue', return_value=CATALOGUE), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                review = core.read_review(paths)
                self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.hg')}, original)
                plan = core.make_plan(review['roots'], 'Main', ['Product:BUILDWALL'], CATALOGUE)
                backups = core.apply_review(review, plan)
                self.assertEqual(len(backups), 4)
                for backup in backups:
                    self.assertEqual(Path(backup).read_bytes(), original[Path(backup).name])
                for path in paths:
                    self.assertEqual(self.files.SaveFile(path).load(), plan['roots'][str(path.resolve())])
                self.assertNotEqual(self.files.SaveFile(paths[0]).load()['Unknown'], self.files.SaveFile(paths[1]).load()['Unknown'])

    def test_currency_only_publication_backups_and_progress(self):
        with tempfile.TemporaryDirectory(prefix='bbe-currency-fixture-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory)
            original = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
            class Progress:
                def __init__(self): self.events = []
                def update(self, fraction, detail=None): self.events.append((fraction, detail))
            with patch.object(core, 'load_catalogue', return_value=CATALOGUE), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                opening, staging, saving = Progress(), Progress(), Progress()
                review = core.read_review(paths, progress=opening)
                self.assertEqual(review['latest_path'], str(max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))))
                plan = core.make_plan(review['roots'], 'Main', [], CATALOGUE,
                                      currencies={'Units': core.CURRENCY_MAX, 'Nanites': 0, 'Quicksilver': 1 << 31}, progress=staging)
                backups = core.apply_review(review, plan, progress=saving)
                self.assertEqual(len(backups), 4)
                for backup in backups:
                    self.assertEqual(Path(backup).read_bytes(), original[Path(backup).name])
                for path in paths:
                    root = self.files.SaveFile(path).load()
                    self.assertEqual(root, plan['roots'][str(path.resolve())])
                    self.assertEqual(core.currency_value(root, 'Main', 'Units'), core.CURRENCY_MAX)
                for progress in (opening, staging, saving):
                    fractions = [event[0] for event in progress.events]
                    self.assertEqual(fractions, sorted(fractions))
                    self.assertEqual(fractions[0], 0.)
                    self.assertEqual(fractions[-1], 1.)
                    self.assertGreaterEqual(len(fractions), 4)
                # Repeating exactly the same changes is a no-op, not a rewrite.
                review = core.read_review(paths)
                plan = core.make_plan(review['roots'], 'Main', [], CATALOGUE, currencies={'Units': core.CURRENCY_MAX})
                before_noop = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
                with self.assertRaisesRegex(ValueError, 'No changes'):
                    core.apply_review(review, plan)
                self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.hg')}, before_noop)

    def test_conflict_changes_nothing_and_no_backup_publish(self):
        with tempfile.TemporaryDirectory(prefix='bbe-unlock-conflict-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory)
            with patch.object(core, 'load_catalogue', return_value=CATALOGUE), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                review = core.read_review(paths)
                plan = core.make_plan(review['roots'], 'Main', ['Product:BUILDWALL'], CATALOGUE)
                save = self.files.SaveFile(paths[1]); save.json_data = fixture(99); save.save()
                after_external_change = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
                with self.assertRaisesRegex(ValueError, 'changed'):
                    core.apply_review(review, plan)
                self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.hg')}, after_external_change)
                self.assertFalse((directory / 'backups').exists())


class AccountTests(PublicationTests):
    def account_files(self, directory):
        codec = importlib.import_module(editor.__name__ + '.account_unlock_files')
        root = dict(Version=9, UserSettingsData=dict(UnlockedSpecials=['^KEEP'], UnlockedSeasonRewards=[],
                    UnlockedTwitchRewards=['^TWITCH_KEEP'], UnlockedPlatformRewards=[]), Other={'Keep': [1, 2, '星']})
        data = json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\x00'
        # Optional modern account metadata is opaque to this writer and must
        # remain exact, even when it contains stale lengths or zero hashes.
        metadata = bytes(range(256)) + bytes(range(176))
        (directory / 'accountdata.hg').write_bytes(data)
        (directory / 'mf_accountdata.hg').write_bytes(metadata)
        return codec, root

    def reward_catalogue(self):
        catalogue = copy.deepcopy(CATALOGUE)
        catalogue['items'].append(dict(id='BASE_AQUARIUM', name='Aquarium', kind='AccountReward', category='Quicksilver',
            unlock_field='AccountWideSpecials', account_field='UnlockedSpecials', account_id='BASE_AQUARIUM'))
        return catalogue

    def test_account_and_save_plan_publish_together(self):
        with tempfile.TemporaryDirectory(prefix='bbe-account-fixture-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory); codec, original_account = self.account_files(directory)
            catalogue = self.reward_catalogue()
            before = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
            with patch.object(core, 'load_catalogue', return_value=catalogue), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                review = core.read_review(paths)
                self.assertIsNotNone(review['account'])
                plan = core.make_plan(review['roots'], 'Main', ['Product:BUILDWALL', 'AccountReward:BASE_AQUARIUM'], catalogue, review['account']['root'], currencies={'Units': core.CURRENCY_MAX})
                core.validate_plan(review['roots'], plan, catalogue, review['account']['root'])
                self.assertTrue(plan['account_changed'])
                self.assertEqual(plan['account_root']['Other'], original_account['Other'])
                events = []
                progress = types.SimpleNamespace(update=lambda fraction, detail=None: events.append((fraction, detail)))
                backups = core.apply_review(review, plan, progress=progress)
                self.assertEqual([value for value, _ in events], sorted(value for value, _ in events))
                self.assertEqual(events[-1][0], 1.)
                self.assertEqual(len(backups), 6)
                for path in backups:
                    self.assertEqual(Path(path).read_bytes(), before[Path(path).name])
                parsed = codec.read_account(directory)
                self.assertEqual(parsed['root'], plan['account_root'])
                self.assertEqual(parsed['root']['UserSettingsData']['UnlockedTwitchRewards'], ['^TWITCH_KEEP'])
                self.assertEqual((directory / 'mf_accountdata.hg').read_bytes(), before['mf_accountdata.hg'])
                for path in paths:
                    self.assertEqual(core.currency_value(self.files.SaveFile(path).load(), 'Main', 'Units'), core.CURRENCY_MAX)

    def test_failed_account_publication_restores_all_six_originals(self):
        with tempfile.TemporaryDirectory(prefix='bbe-account-rollback-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory); self.account_files(directory)
            catalogue = self.reward_catalogue()
            before = {p.name: p.read_bytes() for p in directory.glob('*.hg')}
            with patch.object(core, 'load_catalogue', return_value=catalogue), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                review = core.read_review(paths)
                plan = core.make_plan(review['roots'], 'Main', ['Product:BUILDWALL', 'AccountReward:BASE_AQUARIUM'], catalogue, review['account']['root'])
                with patch.object(self.files.backup_policy, 'finish', side_effect=OSError('Synthetic post-publication failure')), self.assertRaisesRegex(OSError, 'Synthetic'):
                    core.apply_review(review, plan)
                self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.hg')}, before)
                self.assertFalse(list(directory.glob('.bbe-*')))

    def test_plain_account_without_optional_metadata(self):
        with tempfile.TemporaryDirectory(prefix='bbe-account-no-meta-') as temporary:
            directory = Path(temporary); paths = self.make_files(directory); codec, _ = self.account_files(directory)
            (directory / 'mf_accountdata.hg').unlink()
            catalogue = self.reward_catalogue()
            with patch.object(core, 'load_catalogue', return_value=catalogue), patch.object(self.files.backup_policy, 'settings', return_value=(str(directory / 'backups'), 20)):
                review = core.read_review(paths)
                self.assertFalse(review['account']['metadata_exists'])
                plan = core.make_plan(review['roots'], 'Main', ['AccountReward:BASE_AQUARIUM'], catalogue, review['account']['root'])
                core.apply_review(review, plan)
                self.assertFalse((directory / 'mf_accountdata.hg').exists())
                self.assertEqual(codec.read_account(directory)['root'], plan['account_root'])

    def test_missing_account_cannot_be_silently_replaced_with_save_unlock(self):
        catalogue = self.reward_catalogue()
        rows = core.describe_items({'save.hg': fixture()}, 'Main', catalogue)
        self.assertFalse(rows[-1]['supported'])
        with self.assertRaisesRegex(ValueError, 'account'):
            core.make_plan({'save.hg': fixture()}, 'Main', ['AccountReward:BASE_AQUARIUM'], catalogue)


if __name__ == '__main__': unittest.main()
