import pytest
from alc_web.store import Store
from alc_web.recovery import transient_provider_failure


@pytest.mark.parametrize('status,expected',[(429,True),(503,True),(402,False),(401,False),(404,False)])
def test_http_recovery_classification(status,expected):
    assert transient_provider_failure({'details':{'http_status':status}}) is expected


def test_recovery_is_bounded_and_never_resumes_user_pause(tmp_path):
    s=Store(tmp_path);j=s.create({'automatic_recovery':True});jid=j['id']
    for attempt,delay in enumerate([30,60,120],1):
        s.update(jid,state='needs_input',control=None,error={'code':'provider_timeout'})
        assert s.schedule_recovery(jid,now=1000)
        assert not s.schedule_recovery(jid,now=1000)
        assert s.resume_due_recoveries(now=1000+delay-1)==0
        assert s.resume_due_recoveries(now=1000+delay)==1
        assert s.get(jid)['detail']['auto_recovery']['attempts']==attempt
    s.update(jid,state='needs_input',error={'code':'provider_timeout'})
    assert not s.schedule_recovery(jid,now=2000)
    other=s.create({'automatic_recovery':True})['id']
    s.update(other,state='needs_input',error={'code':'provider_timeout'})
    assert s.schedule_recovery(other,now=2000)
    s.control(other,'pause')
    assert s.resume_due_recoveries(now=9999)==0
    assert s.get(other)['state']=='paused'


def test_old_jobs_and_changed_errors_do_not_auto_resume(tmp_path):
    s=Store(tmp_path);old=s.create({})['id']
    s.update(old,state='needs_input',error={'code':'provider_timeout'})
    assert not s.schedule_recovery(old,now=1)
    new=s.create({'automatic_recovery':True})['id']
    s.update(new,state='needs_input',error={'code':'provider_timeout'})
    assert s.schedule_recovery(new,now=1)
    s.update(new,error={'http_status':402})
    assert s.resume_due_recoveries(now=1000)==0
