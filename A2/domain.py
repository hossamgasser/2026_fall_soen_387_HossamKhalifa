class Status:
    HELD = "held"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"


class Reservation:
    def __init__(self, id, eventId, created_at, status= Status.HELD, expires_at=None):
        self.id = id 
        self.eventId = eventId
        self.created_at = created_at
        self.status = status
        self.expires_at = expires_at

    def status_at(self, now):
        if self.status == Status.HELD and now >= self.expires_at:
            return Status.EXPIRED
        return self.status

    
    def is_live_hold(self, now):
        return self.status_at(now) == Status.HELD

class Waitlist_Entry:
    def __init__(self, id, userId, position, createdAt):
        self.id = id
        self.userId = userId
        self.position = position
        self.createdAt = createdAt

class Event:
    def __init__(self, id, title, capacity):
        self.id, self.title, self.capacity = id, title, capacity
        self.reservations = {}                # id -> Reservation
        self.waitlist = {}

    def seats_left(self, now):
        # THE rule, stated ONCE -- no duplicate formula to drift
        taken = sum(1 for r in self.reservations.values()
                        if r.status == Status.CONFIRMED or r.is_live_hold(now))
        return self.capacity - taken

    def hold(self, res_id, now, ttl):
        if self.seats_left(now) <= 0:
            raise SoldOut()
        r = Reservation(res_id,self.id, now, Status.HELD, expires_at=now + ttl)
        self.reservations[res_id] = r
        return r

    def cancel(self, res_id, now):
        r = self.reservations.get(res_id)
        if r is None:
            raise NotFound()

        
        if r.status_at(now) == Status.EXPIRED:
            raise ReservationExpired()
        if r.status_at(now) == Status.RELEASED:
            raise ReservationReleased()


        r.status = Status.RELEASED            # frees a seat by construction
        return r

    def confirm(self, res_id, now):
        r = self.reservations.get(res_id)
        if r is None:
            raise NotFound()

        if r.status_at(now) == Status.EXPIRED:
            raise ReservationExpired()
        if r.status_at(now) == Status.RELEASED:
            raise ReservationReleased()
        
        r.status = Status.CONFIRMED           # takes a seat
        return r

    
    def join_waitlist(self, entry_id, user_id, now):
        if self.seats_left(now) > 0:
            raise EventNotFull()
        if any(e.userId == user_id for e in self.waitlist.values()):
            raise AlreadyOnWaitlist()
        next_key = max((e.position for e in self.waitlist.values()), default=0) + 1
        entry = Waitlist_Entry(entry_id, user_id, next_key, now)
        self.waitlist[entry_id] = entry
        return entry

    def waitlist_rank(self, entry_id):
        ordered = sorted(self.waitlist.values(), key=lambda e: e.position)
        for i, e in enumerate(ordered):
            if e.id == entry_id:
                return i + 1
        raise EntryNotFound()

    def leave_waitlist(self, entry_id):

        w = self.waitlist.get(entry_id)
        if w is None:
            raise EntryNotFound()

        self.waitlist.pop(entry_id)
       


class DomainError(Exception): 
    code = None


class EventNotFound(DomainError):   code = "event_not_found"

# reservations: keep the Assignment 1 code so old clients see no change
class NotFound(DomainError):               code = "not_found"
class SoldOut(DomainError):                code = "sold_out"


# waitlist
class EventNotFull(DomainError):           code = "event_not_full"
class AlreadyOnWaitlist(DomainError):      code = "already_on_waitlist"
class EntryNotFound(DomainError):          code = "entry_not_found"


# lifecycle (new)
class ReservationExpired(DomainError):     code = "reservation_expired"
class ReservationReleased(DomainError):    code = "reservation_already_released"





EVENTS = {
    "ev_101": Event("ev_101", "Jazz Ensemble: Fall Concert", 3),
    "ev_102": Event("ev_102", "Improv Night", 1),
}

_counter = [0]

def _next_id():
    _counter[0] += 1
    return f"res_{_counter[0]}"


def find_reservation_event(res_id):
    for ev in EVENTS.values():
        r = ev.reservations.get(res_id)
        if r is not None:
            return ev, r
    raise NotFound()

def find_waitlist_entry_event(waitlist_entry_id):
    for ev in EVENTS.values():
        w = ev.waitlist.get(waitlist_entry_id)
        if w is not None:
            return ev, w
    raise EntryNotFound()