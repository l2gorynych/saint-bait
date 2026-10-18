from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from saint_bait.catch_journal import CatchJournal
from saint_bait.telemetry.equipment import EquipmentItem
from saint_bait.telemetry.scene import SceneView
from saint_bait.rods import RodView,RodPhase


class CatchJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'catches.sqlite3'
        self.journal=CatchJournal(self.path)
        self.scene=SceneView(waterbody_id='lake_a',coordinates=(71,87))
        self.rod=RodView('rod','feeder',active=True,phase=RodPhase.CASTING,clip_m=8,
                         equipment=(EquipmentItem('bait','worm'),EquipmentItem('rod','picker')))

    def result(self,scene=None,rod=None):
        self.journal.observe(replace(scene or self.scene,catch_id='result',catch_ready=True,
                                    catch_species='c.roach',catch_weight_g=667,catch_grade=2),
                             [rod or replace(self.rod,phase=RodPhase.CATCH)],'generation')

    def test_manual_catch_records_cast_point_bait_and_clip_once(self):
        self.journal.observe(self.scene,[self.rod],'generation')
        # Changing the clip and moving while retrieving must not rewrite cast context.
        moved=replace(self.scene,coordinates=(90,90))
        waiting=replace(self.rod,phase=RodPhase.DEPLOYED,clip_m=17)
        self.journal.observe(moved,[waiting],'generation')
        self.result(moved,replace(waiting,phase=RodPhase.CATCH,equipment=()))
        self.result(moved)
        rows=self.journal.pending()
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['waterbody_id'],rows[0]['x'],rows[0]['y'],rows[0]['clip_m'],rows[0]['bait_id']),
                         ('lake_a',71,87,8,'worm'))
        self.assertNotIn('login',rows[0]);self.assertNotIn('password',rows[0])

    def test_reconnect_at_open_result_does_not_duplicate(self):
        self.result()
        identifier=self.journal.pending()[0]['id']
        self.journal=CatchJournal(self.path)
        self.result()
        self.assertEqual([row['id'] for row in self.journal.pending()],[identifier])

    def test_reused_dialog_address_on_next_identical_fish_is_a_new_catch(self):
        self.result()
        self.journal.observe(self.scene,[self.rod],'generation')
        self.result()
        self.assertEqual(len(self.journal.pending()),2)

    def test_missing_coordinates_stay_local_and_are_not_invented(self):
        self.result(replace(self.scene,coordinates=None))
        self.assertEqual(self.journal.pending(),[])
        with self.journal.connect() as db:self.assertEqual(db.execute('select count(*) from catches').fetchone()[0],1)

    def test_nearby_requires_same_water_and_both_axes_with_inclusive_three(self):
        self.result()
        self.assertEqual(len(self.journal.nearby('lake_a',74,90)),1)
        self.assertEqual(self.journal.nearby('lake_a',75,87),[])
        self.assertEqual(self.journal.nearby('lake_b',71,87),[])

    def test_synced_records_remain_in_local_history_but_leave_outbox(self):
        self.result();identifier=self.journal.pending()[0]['id']
        self.journal.mark_synced([identifier])
        self.assertEqual(self.journal.pending(),[])
        self.assertEqual(len(self.journal.nearby('lake_a',71,87)),1)

    def test_next_cast_updates_clip_and_location(self):
        self.journal.observe(self.scene,[self.rod],'generation');self.result()
        next_scene=replace(self.scene,coordinates=(44,55))
        next_rod=replace(self.rod,clip_m=17)
        self.journal.observe(next_scene,[next_rod],'generation');self.result(next_scene,next_rod)
        self.assertEqual(self.journal.nearby('lake_a',44,55)[0]['clip_m'],17)
