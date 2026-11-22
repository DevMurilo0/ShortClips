import unittest
from shortforge.scoring import pick_segments,extract_heatmap
from shortforge.pipeline import validate_url

class ScoringTests(unittest.TestCase):
    def test_heatmap(self):
        points=extract_heatmap({'heatmap':[{'start_time':100,'end_time':110,'value':.9},
                                            {'start_time':30,'end_time':40,'value':.5}]})
        self.assertEqual(len(points),2)
        clips=pick_segments(500, count=2,clip_seconds=45,heatmap=points)
        self.assertEqual(len(clips),2)
        self.assertTrue(all(x.length>=30 for x in clips))
        self.assertTrue(all(x.end<=500 for x in clips))
        self.assertTrue(all('Mais reproduzido' in x.reason for x in clips))

    def test_audio_without_heatmap(self):
        energy=[.1]*400
        for i in range(140,160):energy[i]=1.8
        for i in range(300,315):energy[i]=1.4
        clips=pick_segments(400,count=2,clip_seconds=45,energies=energy)
        self.assertEqual(len(clips),2)
        self.assertTrue(all('não é Most Replayed' in x.reason for x in clips))

    def test_short_video_limit(self):
        with self.assertRaises(ValueError):pick_segments(12)
        clips=pick_segments(40,count=1,clip_seconds=45)
        self.assertEqual(clips[0].length,40)

    def test_url_validation(self):
        self.assertEqual(validate_url('https://youtu.be/kVy8zSfuRc0'), 'https://youtu.be/kVy8zSfuRc0')
        for u in ['file:///etc/passwd','https://evil.example','https://youtube.com.evil.org/watch?v=x','https://youtube.com/@canal']:
            with self.assertRaises(ValueError):validate_url(u)

if __name__=='__main__':unittest.main()

class IntervalRegressionTests(unittest.TestCase):
    def test_durations_and_nonoverlap(self):
        for duration in (30,31,40,60,90,180,500,7536):
            for target in (5,30,45,60,100):
                clips=pick_segments(duration,5,target)
                for clip in clips:
                    self.assertGreaterEqual(clip.length,30);self.assertLessEqual(clip.length,60)
                    self.assertGreaterEqual(clip.start,0);self.assertLessEqual(clip.end,duration)
                for a,b in zip(clips,clips[1:]):self.assertLessEqual(a.end,b.start+.01)
    def test_nonfinite_duration(self):
        for value in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):pick_segments(value)


class EmptyReplayTests(unittest.TestCase):
    def test_zero_heatmap_does_not_claim_replay_selection(self):
        self.assertEqual(extract_heatmap({'heatmap':[{'start_time':0,'end_time':60,'value':0}]}),[])
