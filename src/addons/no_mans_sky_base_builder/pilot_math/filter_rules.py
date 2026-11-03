"""Decoded player-IK category rule; no game access and no asset-name rules.

This is the default native category predicate, not a substitute for proving
that an asset's collider is instantiated and active in the relevant world.
"""
PLAYER_IK_QUERY_CATEGORY = 64
BODY_CATEGORY_NAMES = (
    'Normal','Terrain','TerrainInstance','TerrainActivated','Trigger','Water',
    'Substance','Asteroid','Player','NetworkPlayer','NetworkPlayerNoCargoPermission',
    'NPC','Ragdoll','Vehicle','Vehicle_Piloted','Vehicle_BedFloor','Vehicle_BedWall',
    'Vehicle_Wheels','VehicleToVehicle','Creature','Spaceship','Spaceship_Landing',
    'Spaceship_CargoBarrier','Debris','Shield','Loot','PlayerMovableObject',
    'NetworkedObjectNoPermission','SolarSystemMapObject','TriggerLocalPlayer',
    'CollidesWithNothing','CollidesWithEverything')
PLAYER_IK_ADMITTED_BODY_CATEGORIES = frozenset((0,1,2,3,13,20,26,31))


def player_ik_body_admitted(flags54, category_info90):
    """Exact current native primary-body predicate from 142d1efd0.

    Ignore/allow masks attached to a body are intentionally absent: the
    native helpers bypass these when the query category is >=32. Native
    body registration/validity and shape activation are separate checks.
    """
    category=int(category_info90)&0x7f
    if category>=32:
        raise ValueError('Expected a native primary body category 0..31')
    return not bool(int(flags54)&0x20) and category in PLAYER_IK_ADMITTED_BODY_CATEGORIES


def initial_component_category(component):
    """Derive the proven default category, or return None with a reason.

    NoPlayerCollide changes the body ignore mask, not the foot-IK category.
    Runtime category overrides and dynamic activation remain caller inputs.
    """
    fields=component['fields'];kind=component['component']
    if fields.get('TriggerVolume')!='false':
        return None,'Trigger-body construction flags not ported'
    if kind=='TkStaticPhysicsComponentData':
        if fields.get('UseAsteroidCollision')=='true':return 7,None
        return 0,None
    if kind=='TkPhysicsComponentData':
        if fields.get('IgnoreAllCollisions')!='false':
            return None,'IgnoreAllCollisions construction not ported'
        if fields.get('DisablePhysicsUntilGravGunned')!='false':
            return None,'Activation depends on live grav-gun state'
        name=fields.get('CollisionGroup')
        if name in BODY_CATEGORY_NAMES:return BODY_CATEGORY_NAMES.index(name),None
        return None,'Unknown collision group'
    return None,'Unsupported native physics component'


def select_native_ray_hits(hits,capacity=32,deduplicate_bodies=False):
    """Native wrapper ordering/capacity after shape-level hit emission.

    Input hits must already represent the native shape collector's emissions.
    Raw triangle intersections do not establish that contract. The observed
    foot queries use capacity32 and deduplicate_bodies=False. Native sorting
    is unstable for equal distances; callers must handle consequential ties.
    """
    if not 0<capacity<=64:raise ValueError('Native capacity must be 1..64')
    ordered=sorted(hits,key=lambda hit:hit['fraction'])
    if deduplicate_bodies:
        seen=set();filtered=[]
        for hit in ordered:
            key=hit['body_key']
            if key not in seen:seen.add(key);filtered.append(hit)
        ordered=filtered
    return ordered[:capacity]


def native_hit_filter(body_handle, *, body_valid=True, body_flags8c=1,
        excluded_handles=(), userdata_mask2c0=None, userdata_flags31a=0,
        reject_mask=0, required_mask=0, reject_flag31a_bit3=False,
        hit_class=1, accept_hit_class2=True):
    """Decoded NMS output filter after native category admission.

    Handles are opaque uint64 values, not Havok body indices. A nonzero
    required mask needs any overlapping bit. Ordinary captured foot queries
    have no exclusions/masks, accept class2, and do not reject flag31a bit3.
    This function does not establish runtime activation or shape emission.
    """
    if hit_class not in (1,2):
        raise ValueError('Only native wrapper hit classes 1 and 2 are covered')
    if not body_valid or not (int(body_flags8c)&1):return False
    handle=int(body_handle)&0xffffffffffffffff
    if handle!=0xffffffffffffffff and handle in {int(h)&0xffffffffffffffff for h in excluded_handles}:
        return False
    if userdata_mask2c0 is not None:
        if reject_flag31a_bit3 and int(userdata_flags31a)&8:return False
        if int(userdata_mask2c0)&int(reject_mask):return False
    if required_mask and (userdata_mask2c0 is None or not (int(userdata_mask2c0)&int(required_mask))):
        return False
    return hit_class!=2 or accept_hit_class2
