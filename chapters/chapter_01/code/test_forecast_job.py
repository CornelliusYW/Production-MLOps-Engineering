import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import forecast_job as job


class MorningJobTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root=Path(self.scratch.name)
        self.files=self.root/'files';self.files.mkdir()
        self.output=self.root/'published'
        for name in ['service.json','assortment.csv','sales_history.csv','fallback_forecasts.csv']:
            shutil.copy2(job.HERE/name,self.files/name)

    def run_job(self,case='on-time',**kwargs):
        return job.run_job(case,self.output,self.files,**kwargs)

    def change_csv(self,name,change):
        path=self.files/name
        with path.open(newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        change(rows)
        with path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

    def test_normal_run_creates_eight_computed_forecasts(self):
        result=self.run_job()
        self.assertEqual((result['status'],result['primary'],result['fallback']),('published',8,0))
        _,rows=job.read_publication(self.output,'2026-01-06',self.files)
        self.assertEqual(rows[0]['forecast_units'],'100.00')
        self.assertEqual(sum(float(r['forecast_units']) for r in rows),850)
        self.assertTrue((self.output/result['input_snapshot']).exists())

    def test_late_north_feed_uses_independent_fallback(self):
        result=self.run_job('late-feed')
        self.assertEqual((result['primary'],result['fallback'],result['manual']),(4,4,[]))
        _,rows=job.read_publication(self.output,'2026-01-06',self.files)
        self.assertEqual((rows[0]['forecast_units'],rows[0]['method'],rows[0]['reason']),('90.00','fallback','late_feed'))
        self.assertEqual(rows[-1]['method'],'primary')

    def test_unavailable_fallback_does_not_replace_publication(self):
        self.run_job();before=(self.output/'current.json').read_bytes()
        self.change_csv('fallback_forecasts.csv',lambda rows: rows[0].update(available_at='2026-01-05T04:40:00+07:00'))
        result=self.run_job('late-feed')
        self.assertEqual(result['status'],'not_published')
        self.assertEqual(len(result['manual']),1)
        self.assertEqual((self.output/'current.json').read_bytes(),before)

    def test_wrong_target_fallback_cannot_fill_gap(self):
        self.change_csv('fallback_forecasts.csv',lambda rows: rows[0].update(target_date='2026-01-05'))
        result=self.run_job('late-feed')
        self.assertEqual(result['status'],'not_published')
        self.assertFalse((self.output/'current.json').exists())

    def test_deadline_miss_does_not_publish(self):
        result=self.run_job(now='2026-01-05T06:01:00+07:00')
        self.assertEqual((result['status'],result['reason']),('not_published','deadline_missed'))
        self.assertFalse((self.output/'current.json').exists())

    def test_same_job_and_planning_load_are_repeatable(self):
        self.run_job();before=(self.output/'current.json').read_bytes()
        self.assertTrue(self.run_job()['reused'])
        self.assertEqual((self.output/'current.json').read_bytes(),before)
        a=job.load_planning(self.output,'2026-01-06',self.files)
        b=job.load_planning(self.output,'2026-01-06',self.files)
        self.assertEqual((a['created'],b['created'],b['refreshed'],b['total_for_date']),(8,0,8,8))

    def test_planner_decision_survives_forecast_refresh(self):
        self.run_job();job.load_planning(self.output,'2026-01-06',self.files)
        path=self.output/'planning_tasks.json';tasks=json.loads(path.read_text())
        key='S001|P001|2026-01-06';tasks[key]['approved_order']=75
        path.write_text(json.dumps(tasks))
        self.run_job('late-feed');job.load_planning(self.output,'2026-01-06',self.files)
        self.assertEqual(json.loads(path.read_text())[key]['approved_order'],75)
        self.assertEqual(json.loads(path.read_text())[key]['method'],'fallback')

    def test_reader_rejects_wrong_date_or_modified_file(self):
        result=self.run_job()
        with self.assertRaisesRegex(ValueError,'wrong target'):
            job.read_publication(self.output,'2026-01-07',self.files)
        (self.output/result['batch_file']).write_text('broken')
        with self.assertRaisesRegex(ValueError,'contents have changed'):
            job.load_planning(self.output,'2026-01-06',self.files)
        self.assertFalse((self.output/'planning_tasks.json').exists())

    def test_publication_write_failure_keeps_previous_batch(self):
        self.run_job();before=(self.output/'current.json').read_bytes()
        real_write=job.atomic_write
        def fail_pointer(path,content):
            if Path(path).name=='current.json':raise OSError('simulated interrupted publication')
            return real_write(path,content)
        with patch.object(job,'atomic_write',side_effect=fail_pointer):
            with self.assertRaises(OSError):self.run_job('late-feed')
        self.assertEqual((self.output/'current.json').read_bytes(),before)
        _,rows=job.read_publication(self.output,'2026-01-06',self.files)
        self.assertTrue(all(r['method']=='primary' for r in rows))

    def test_invalid_or_duplicate_history_is_rejected(self):
        self.change_csv('sales_history.csv',lambda rows: rows[0].update(units='NaN'))
        with self.assertRaises(ValueError):self.run_job()
        shutil.copy2(job.HERE/'sales_history.csv',self.files/'sales_history.csv')
        self.change_csv('sales_history.csv',lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValueError,'duplicate history'):self.run_job()


if __name__=='__main__':unittest.main()
