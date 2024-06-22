import datetime
import os
from math import ceil
from unittest import mock

import openai
from django.urls import reverse
from factory.django import FileField
from lxml import etree

from cl.audio.factories import AudioFactory, AudioWithParentsFactory
from cl.audio.management.commands.transcribe import (
    audio_can_be_processed_by_open_ai_api,
    transcribe_from_open_ai_api,
)
from cl.audio.models import Audio, AudioTranscriptionMetadata
from cl.audio.utils import transcription_was_hallucinated
from cl.lib.test_helpers import SitemapTest
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES
from cl.tests.utils import MockResponse


class PodcastTest(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court_1 = CourtFactory(
            id="ca9",
            full_name="Court of Appeals for the Ninth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA9.",
        )
        cls.court_2 = CourtFactory(
            id="ca8",
            full_name="Court of Appeals for the Eighth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA8.",
        )
        with mock.patch(
            "cl.lib.es_signal_processor.allow_es_audio_indexing",
            side_effect=lambda x, y: True,
        ), cls.captureOnCommitCallbacks(execute=True):
            cls.audio = AudioWithParentsFactory.create(
                docket=DocketFactory(
                    court=cls.court_1, date_argued=datetime.date(2014, 8, 16)
                ),
                local_path_mp3__data=ONE_SECOND_MP3_BYTES,
                local_path_original_file__data=ONE_SECOND_MP3_BYTES,
                duration=1,
            )
            cls.audio_2 = AudioWithParentsFactory.create(
                docket=DocketFactory(
                    court=cls.court_1, date_argued=datetime.date(2016, 8, 17)
                ),
                local_path_mp3__data=SMALL_WAV_BYTES,
                local_path_original_file__data=SMALL_WAV_BYTES,
                duration=0,
            )
            AudioWithParentsFactory.create(
                docket=DocketFactory(court=cls.court_2),
                local_path_mp3__data=SMALL_WAV_BYTES,
                local_path_original_file__data=SMALL_WAV_BYTES,
                duration=5,
            )

    async def test_do_jurisdiction_podcasts_have_good_content(self) -> None:
        """Can we simply load a jurisdiction podcast page?"""

        # Test jurisdiction_podcast for a court.
        response = await self.async_client.get(
            reverse(
                "jurisdiction_podcast",
                kwargs={"court": self.court_1.id},
            )
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 2),
            ("//channel/item/title", 2),
            ("//channel/item/enclosure/@url", 2),
        )
        xml_tree = self.assert_es_feed_content(
            node_tests, response, namespaces
        )

        # Confirm items are ordered by dateArgued desc
        pub_date_format = "%a, %d %b %Y %H:%M:%S %z"
        first_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[1]/pubDate")[0].text  # type: ignore
        )
        second_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[2]/pubDate")[0].text  # type: ignore
        )
        first_item_pub_date_dt = datetime.datetime.strptime(
            first_item_pub_date_str, pub_date_format
        )
        second_item_pub_date_dt = datetime.datetime.strptime(
            second_item_pub_date_str, pub_date_format
        )
        self.assertGreater(
            first_item_pub_date_dt,
            second_item_pub_date_dt,
            msg="The first item should be newer than the second item.",
        )

        # Test all_jurisdictions_podcast
        response = await self.async_client.get(
            reverse(
                "all_jurisdictions_podcast",
            )
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 3),
            ("//channel/item/title", 3),
            ("//channel/item/enclosure/@url", 3),
        )
        self.assert_es_feed_content(node_tests, response, namespaces)

    def test_do_search_podcasts_have_content(self) -> None:
        """Can we make a search podcast?

        Search podcasts are a subclass of the Jurisdiction podcasts, so a
        simple test is all that's needed here.
        """

        params = {
            "q": f"court_id:{self.audio.docket.court.pk}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(xml_tree.xpath("//channel/item"))  # type: ignore
        expected_item_count = 2
        self.assertEqual(
            node_count,
            expected_item_count,
            msg="Did not get {expected} node(s) during search podcast "
            "generation. Instead found: {actual}".format(
                expected=expected_item_count, actual=node_count
            ),
        )
        # pubDate key must be present in Audios with date_argued.
        pubdate_present = xml_tree.xpath(
            "count(//item[pubDate]) = count(//item)"
        )
        self.assertTrue(pubdate_present)

        # Confirm items are ordered by dateArgued desc
        pub_date_format = "%a, %d %b %Y %H:%M:%S %z"
        first_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[1]/pubDate")[0].text  # type: ignore
        )
        second_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[2]/pubDate")[0].text  # type: ignore
        )
        first_item_pub_date_dt = datetime.datetime.strptime(
            first_item_pub_date_str, pub_date_format
        )
        second_item_pub_date_dt = datetime.datetime.strptime(
            second_item_pub_date_str, pub_date_format
        )
        self.assertGreater(
            first_item_pub_date_dt,
            second_item_pub_date_dt,
            msg="The first item should be newer than the second item.",
        )

        # pubDate key must be omitted in Audios without date_argued.
        with self.captureOnCommitCallbacks(execute=True):
            self.audio.docket.date_argued = None
            self.audio.docket.save()
            self.audio_2.docket.date_argued = None
            self.audio_2.docket.save()
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        pubdate_not_present = xml_tree.xpath(
            "count(//item[not(pubDate)]) = count(//item)"
        )
        self.assertTrue(pubdate_not_present)

    def test_catch_es_errors(self) -> None:
        """Can we catch es errors and just render an empy podcast?"""

        # Bad syntax error.
        params = {
            "q": "Leave /:",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
        )

        # Unbalanced parentheses
        params = {
            "q": "(Leave ",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
        )


class AudioSitemapTest(SitemapTest):
    @classmethod
    def setUpTestData(cls) -> None:
        AudioWithParentsFactory.create(
            local_path_mp3__data=ONE_SECOND_MP3_BYTES,
            local_path_original_file__data=ONE_SECOND_MP3_BYTES,
            duration=1,
            blocked=True,
        )
        AudioWithParentsFactory.create(
            local_path_mp3__data=ONE_SECOND_MP3_BYTES,
            local_path_original_file__data=ONE_SECOND_MP3_BYTES,
            duration=1,
            blocked=False,
        )

    def setUp(self) -> None:
        self.expected_item_count = 1
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": SEARCH_TYPES.ORAL_ARGUMENT}
        )

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()


class TranscriptionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court_1 = CourtFactory(
            id="ca9",
            full_name="Court of Appeals for the Ninth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA9.",
        )

        cls.audio_without_local_path_mp3 = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 16)
            ),
            local_path_mp3=None,
            duration=1,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_bigger_than_limit_duration = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 15)
            ),
            local_path_mp3=FileField(data=b"\x10" * 26_000_000),
            duration=4000,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_1 = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 14)
            ),
            duration=2000,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_to_be_retried = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 13)
            ),
            duration=1000,
            stt_status=Audio.STT_FAILED,
        )
        cls.transcripted_audio_hallucination = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 14)
            ),
            duration=1779,
            # this was an actual transcript: https://www.courtlistener.com/api/rest/v3/audio/92035/
            stt_transcript="""I. The Uncanny Countess    I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS    I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS I. THE UNCANNY COUNTESS This location, some of them are just peculiar people who have never heard of chiseled fish. These are primitive people. If I'm in these fish and I am carrying this step  I shouldn't sit there and just and stand. It seems to me I am already Kyung Hause who's complex or material to be found on fish, which certainly is not my case. Now I am going to take me little steps aboard theчив festival and I am going to set up some table for me to settle down and sit down and just contemplate if I'll be settled in one piece or some other and the question is okay, with a little negativity in me let us try. What if I'm sat on a chair or on a chair and what if this is one one planing picture sitting okay. You get the point? Okay. What color would you like? I'll pick a color. What else would you like? Okay, one of those? Okay. Can you sit on it? Okay. There we go. Where do you need it for? Okay, here? Yeah, okay. Is it up to you? No? Yeah. Okay. So, up so we can hook it around. Okay, pull it up. And hook that end, look at it. Okay. And let's see if that goes up there too.  The leaker doesn't blow any more, but my arms were going to go out of control. So I couldn't do it because my arms were going to, were where I had it last time, so, yeah, I don't know what to call it. We're going to have to figure it out. You're hot. I just want to make sure that it's in the right position. Okay, that's good, that's good. That's good, that's good, that's good, that's good. That's good, that's good, that's good, that's good. That's good, that's good, that's good, that's good. Perfect. Good. Was it the contrary one, the one we talked about the other day? Okay. It's recording. Now it's acting as recording. But actually, I think it kinda interrupts what they're going to be doing. Look, we have a lot of pieces that need to be checked. Hook up the cap. Okay. Okay. Okay. Okay. Okay. Okay. Hold on. Okay. Yes? Yeah. Can you just be quiet? Yeah. Yeah? Okay. Wait. Wait. Right. Hold on. What's that? I got to the right, I got to the right. Hold on. Hold on, wait, I got to get up. What was that? I got to go back. Yeah, yeah. Right, I got to go gone. Be back in, I have another one that's working. Taker? I got to go left, I got to go left. And uh, that girl over there, she has the sock on. Place your hand in here, hold hands with your hands.  Okay, strawberry drink, you're welcome. That's a section on the front and a section on the back. Did you want to tell us anything else, or can we go for another? One other question, did you have a family or colleagues who told you that they were looking at a lady and they had actually seen a woman and they thought that lady didn't look that great and you didn't find out who it is? I think it's a really good question. Can you speak to that a little bit? Absolutely, absolutely. That's a very good question. It's a really good question, because I think it's a perfect example you can look at a woman at a time, because a lot of what we were talking about was actually very, very difficult to determine. You mentioned how it was difficult to do that along with the variety of people there. Can you explain a little bit, a little bit about your work at Harvard, what this means, and what people from these rooms could know about your work as well? And can you talk a little bit about the,  the workforce included? In fact, did anybody who worked in the Laboratory know that you were a student at Harvard? Did anybody know? No? No. Neither did anybody know. Do you know? No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. No. And these were? No, no. Yes sir. And you were a Mucine, and then from there you all ran on down right through Yale. Yes. Does that make no differences in how people realize that you were there and that people actually knew how hard you frame it? No. No, but you still ran for that. What would you have to do to come in and be accepted, what would you conclude to become an instructor? Really, not to go, just to go home and— At least not yet. Not yet. You said all the time you'd never met a player Now that is a little crazy, I've never met that. That's really crazy. All right. We have a pretty good number of questions. What's your usual speech like? No Russell, I don't know. What's your usual speech? I don't really hear it. My usual speech is I don't hear it very well. You vote for yourself. As an individual I never had to worry about what they were going to say they never gave me any music. How does a guy who doesn't suit their language get the job? That's true. But don't you think you're the only person that got the job? I'm the only person that got the job. Is that a statement? Well, I think there's a difference. I do think that the ways in which the statement was made was not a matter of my ability. But I think that my language will maybe work in other ways, but I don't think that the way I was referred to or the way that I was referred to took a little longer to get it. I don't know how long it took. I think it took a certain amount of time. What would it take to get it? I don't think it took a lot of time. If you keep it up... You're about to talk about what we call a literary question. I guess that's my position. But I do think that our view is we should look at listening and ask if we could help all kinds of different voices. I'm not always like,  or for you it sounds good, or for me it doesn't sound good. But if you wanted me to look at it from a different perspective, then I think it's a good idea. I think the second thing that I would like to talk about is the question of how do you get people to read your work? How do you get people to read your work? It's not a difficult question. It's a question of how do you get people to read your work? How do you get people to read your work? How... How do you get... How do you get.... How do you get people to, How do you get... First of all, How do you get people to read your work? Good evening. Well, aren't we fine to have you here? How are you? How have you been? Okay. So, at the back! At the back, thank you. Please come to the platform tocially. He really wants to join in. No, no, what do you want to do? I don't know. Well, do something, you know. What are you going to do? Come on, sit down. Come on. I don't know what it is. Don't get excited. No! Pass, pass, pass, pass.  I saw one. I'm going to be the front this time, isn't that what the question's asking? Yes, sir, yes. Item. Let's go. Keep still, keep going. Keep still. Okay. Questioner 2. Questioner 3. Questioner 4. Questioner 5.""",
            stt_status=Audio.STT_COMPLETE,
        )
        cls.transcripted_audio_not_hallucinated = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 14)
            ),
            duration=1497,
            stt_transcript="United States of America v. Sean Kerwin Bindranauth. And Anshu Bhudrani is here for the appellant. And Audrey Pence Tominelli is here for the United States. And Ms. Bhudrani, you may begin your argument. Thank you, and good afternoon, Your Honors. Anshu, and may it please the Court. Anshu Bhudrani, Assistant Federal Public Defender on behalf of the appellant, Sean Bindranauth. I'd like to focus my argument today on the sentencing enhancements applied in this case, which included a four-level increase for aggravating role, a four-level increase for the business being in the business of laundering funds, and a further two-level increase for engaging in sophisticated laundering. The District Court erred in applying these enhancements, requiring reversal and a remand for resentencing. With regard to the aggravating role enhancement that was applied, the Court must first determine the size of the alleged criminal, enterprise, or organization at issue in the case. And Section 3B1.1 applies only where the defendant was the organizer, leader, manager, or supervisor of one or more participants, which itself is a very specifically defined term by the responsible for the commission of the offense. That is, participants are those individuals who can actually be held criminally liable for the offense. And here, there's no such finding by the Court, or really any argument by the government, that the individuals relied upon by Sean in this case could be held criminally responsible for the money laundering scheme. The guideline says it can be applicable. You don't need five or more people. The guideline says if the activity was extensive, otherwise extensive. And here, we have evidence that there was a criminal activity that lasted for 18 months. There were a lot of victims sending money to your client, and then funnel the money to Nigeria. That seems pretty extensive. An 18-month criminal conduct involving a lot of defendants. Why is it that extensive? So, Your Honor, I don't believe you get to the question of whether the enterprise was otherwise extensive until you first determined whether there were any participants being organized, led, managed, or supervised by Mr. Bindranoth. And in this case, the individuals... But didn't he have... Isn't there testimony or evidence that he, after a couple of banks closed his accounts, that he then started using family and friends and paying them in order to deposit funds into accounts? So that is the allegation. However, the definition that the government would need to have met in this case of participant is that the individuals must be able to be held criminally responsible for the commission of the offense. And here, their testimony and the government's own argument indicates otherwise. And so, if I may just go through the testimony. Two individuals who helped Sean wire money testified at trial. One in the government's case-in-chief and one in the defendant's case-in-chief. And both disavowed, under oath, any knowledge of the fraudulent scheme of the wire fraud or any of where the source of the funds or that they were being... The transactions were designed to conceal the source of the funds. His friend, I think, testified that he believed the money was Sean's and that it was being transferred to Nigeria to help a sick family member. His aunt testified... Disbelieved those pieces of testimony? Well, those were the facts that were also presented at the sentencing and propounded in favor of applying this enhancement. And if the court were to have disbelieved those factual or their testimony, there's still nothing in the record to support that by law, or at least under the guidelines definition of what a participant is, that these individuals could be held criminally responsible for the money laundering scheme. And in fact, the government didn't even believe them to be participants by that definition of the word because the government referred to these individuals as victims in their seeking of the vulnerable victim enhancement in this case. And so it's difficult to sort of conceive of them as both victims of the offense, but also perpetrators of the offense. And it's because they were victims. The way I read the guideline is you don't need other people involved as long as it's extensive. I don't believe that's correct. And there is a case that I think supports our position, along with another piece of commentary from the guidelines. And he did use his mom and his aunt to help him out too, didn't he? Yeah. So we're not disputing that individuals wired money at his request. I think the dispute here is about whether they can be considered participants under the definition of the guideline. That is, whether they can be held criminally responsible, whether they had the mens rea. The conduct is extensive and it only involves him. You're saying the aggravated role enhancement cannot apply? Not to him because he wasn't the leader, organizer, manager, supervisor of anyone below him. And so it doesn't mean that he wasn't a participant in a criminal enterprise or that there weren't people above him directing him. You're saying that him directing individuals. So after he opened an account with Iberia Bank, the bank closed the account almost immediately because they were concerned that it was suspicious and they were concerned with the rapid movement of funds and unusual wire transfer. Then he opened a Bank of America account. Then he opened a Wells Fargo account, which the bank closed the next month because of suspected fraud. And Wells Fargo notified him that they were concerned that he was doing transfers that were unauthorized. And that's why the bank closed his account. And then he started using individuals in order to deposit funds into accounts. How can you say that he was not directing them? I'm having a very hard time with your argument. Let me try and clarify. So the bank accounts and the closing of the bank accounts and the opening of bank accounts, those go to his potential mens rea regarding the money laundering and his knowledge of the wire fraud offense. For the leader organizer enhancement to apply, for him to get an aggravating role in this offense, he needs to have himself led, organized, managed, supervised people below him. And the guidelines have a very specific definition for participants. I looked up the guideline and I'm not sure I understand your definition. It says, if the defendant was an organizer or leader of a criminal activity that involved five or more participants or was otherwise extensive, increased by four levels. So you indicated to Judge Wilson that you have to have five participants first. It doesn't sound like that. You have to have one participant. And our argument is that there were no participants below him when applying that definition. If we read that again, you have to be either a leader or an organizer. So you don't really need him to be a leader. He could be an organizer. Right. But it still doesn't do away with the requirement that there be participants. If I may point you to a case out of this circuit that I think helps. I have one more factual question. Why wouldn't the scammers in Nigeria count as participants for these purposes? Because they were not, they were not, they weren't involved in the money laundering part of the scheme in terms of like the wiring of the money. The evidence the government relied upon in propounding this enhancement was that he led and organized, managed, and supervised these alleged 20 individuals in like dropping them, like the actions that they're relying upon are that he took them to Western Union and MoneyGram, told them to go in and wire the money and they came out. And then for some of them, he potentially paid them $20. So that's the scheme. Everyone in Nigeria sort of sits above Mr. Bindernoth in this scheme and is involved in the wire fraud portion of the scheme. But the money laundering, the sort of accepting of the deposits, and then the wiring of the funds to Nigeria was done by Mr. Bindernoth. And so those are the individuals that are properly considered when, when considering this, the application of this enhancement. And I think. So you had a case that supports that proposition? Yeah. So we relied on it in our briefing, United States v. Williams. It's a case where a husband and wife were charged for wire fraud for using federal grant money on, in an unauthorized manner. And the husband was charged and acquitted. The wife was found guilty. And with regard to the aggravating role enhancement as to the wife, this court reversed application of the aggravating role enhancement, finding that the husband was not a participant as that word is defined under the guidelines. And this is a quote, the factual findings do not go so far as to establish by a preponderance of the evidence that the husband was a criminally culpable participant in his wife's wire fraud, because his intent to defraud and steal is a requisite threshold question for determining his criminal responsibility. And if you don't have that, they're not technically considered participants and therefore cannot be considered for the aggravating role enhancement. And our have the requisite criminal mens rea in order to be found criminally culpable for a money laundering offense and therefore enhancing Mr. Bindranath's role in the offense on behalf of these individuals was error by the court. And he should not have received an aggravating role. If I may also turn to the sophisticated laundering. Can you give me the citation again for that case? Sure. It is 527 F3D 1235. And it's cited at page 29 of the initial brief. Thank you. We also believe it was error for the court to apply the sophisticated laundering enhancement here. Sophisticated laundering, you know, usually involves complex or intricate offense conduct pertaining to the execution or concealment of the money laundering scheme. And here the district court sort of seemed to conflate the sophistication of the underlying wire fraud scheme with the non sophistication of the money laundering scheme at issue here. And for that reason, this enhancement was also improperly applied. Didn't he use layering to move the money around, which involves an extra step in the process? So our argument as to that is that this wasn't layering in the typical sense of having shell corporations or offshore accounts or multiple accounts. He had, you know, the reason he engaged his friends and family to help him out here was because he himself was banned from Western Union and MoneyGram from effectuating these transactions in his own name because of suspected fraud. And so he used friends and family that are easily traceable to him. You know, concealment money laundering at a minimum involves some level of using other people to conceal funds. It's sort of like the base level. And so to apply a sophisticated laundering enhancement in this particular circumstance seems particularly not in keeping with the commission's intended use of this because this scheme could not have been less sophisticated if it tried to be. So I see my time is running. And so for those reasons, we would ask that you reverse and remand. All right. Thank you, counsel. We'll hear from Ms. Tominelli on behalf of the government. Good afternoon, your honors, and may it please the court. My name is Audrey Pence Tominelli on behalf of the United States. And seated with me at council table is Assistant United States Attorney Lindsay Lizopoulos-Friedman, who tried the case. The standard of review is decisive for all three of the sentencing enhancement issues. Under the high standard of clear error, the appellant cannot show that there is no evidence supporting the district court's factual findings, which were made on the record with justification. And I'll start right where we left off on sophisticated laundering. On the issue of sophisticated laundering, as your honor pointed out, there was layering in this instance, which is specifically noted in the commentary as one example of sophisticated laundering. This appellant directed and paid more than only family and friends, but actually at least 20 individuals to receive and send money on his behalf as a part of this scheme. And in fact, many of those individuals were unemployed and needed money. Some of them he met through a drug treatment program. And so in terms of sophisticated laundering, certainly the two or more levels here of passing it through other individuals accounts for that. And this is important because the key here with layering is that it makes laundering more difficult for law enforcement to detect. And certainly here that is the case. What about, what about your friend on the other side's argument that this was actually very simple? It was just that since his bank suspected him of some problems, he just kind of outsourced this to other folks, but it wasn't really complicated in the sense that sometimes these transactions are. Well, your honor, I do think there are of course instances where laundering is more complicated and those are some of the examples listed, but that does not change the fact that here there was sophistication just as the district court judge found. And he pointed to the fact that there was layering here, that these are undisputed facts. And it's a conclusion that can be drawn that just because this wasn't the most sophisticated laundering scheme does not mean that it was not sophisticated. How would you make it less sophisticated? Would it be just if he, if he got the money and sent it himself? I believe if there was no layering, we'd be having a different discussion here, but because that's in the commentary as specifically one example of how laundering can be sophisticated, because it does make it more difficult to detect the laundering. I think that if that were not taking place, then certainly this would be a less sophisticated scheme. I'll turn now to the issue of the leader and organizer enhancement. Of course, the district court judge did find that this met both prongs of five or more participants as well as being otherwise extensive. On the issue of whether the individuals directed by the appellant were participants or were criminally responsible, I think it turns back to all of the arguments actually laid out earlier in the brief about the question of mens rea. So either these at least 20 individuals knew that they were sending money that was the proceed of illicit activity, or certainly they had reason to know and avoided asking about it. So I do think that if the question is whether they could have been held criminally responsible and had that mens rea, I think there is sufficient evidence to support that they did. These individuals were picked up, driven to a location, directed to make wire transfers, paid $20, all at the behest of the appellant. What about the fact that they were counted as victims in a certain sense? How can you be both a victim and a perpetrator? Well, Your Honor, I think on the record here, they ultimately were not found to be victims, and the government is not proceeding under that argument and didn't at the time of sentencing. And so I believe that here really what we are looking at is them as co-conspirators that were directed exclusively by the appellant. This was not including others who may have been higher up in this scheme, but really they were directed only by the appellant here. Do you think that higher ups in the scheme, that Nigerians could count as participants under the definition of participant, or do you agree with defense counsel that they could not? I think the question is whether he was a leader or directing certain participants. If that is the issue at stake, then I don't think necessarily that he was. But if we're looking at the scheme as a whole, of course they were participants. So maybe for purposes of considering whether it was extensive rather than whether he was directing a certain number of participants. Certainly, Your Honor. And I think beyond only that, the time of this scheme, over a year and a half, the amount, at least a million dollars, all coming from Key West to Nigeria, this scheme was definitely otherwise extensive, if not five or more participants. If Your Honors have, oh, I apologize. Oh, I was going to ask about, this is another case where this district judge makes a premature Keene statement. He says, in the event this matter is before he even calculates what the guideline sentence would be. That's not what we permitted in Keene, is it? Well, Your Honor, I did hear the argument earlier today, and I understand the concerns raised by this court. And so I think the key factor here is that this district court judge did not clearly err on these enhancements. But to your specific question of whether that is what is allowed under Keene, my understanding is there's no temporal restrictions at this point on Keene, although this court- There is no temporal restriction, but the whole point of Keene, a Keene finding, is to tell the district, the appellate court, when we have review, that the sentence is reasonable. So how can we know that a district court has made a reasonable determination on the sentence when, in this case, he hasn't even heard anything? I mean, he made this, he made that finding at the beginning of the sentencing hearing. Your Honor, I, my reading of the statement that he makes is, you know, this is a district court judge who sat through a whole trial, and my reading is that he's directing the parties of really where to focus. Knowing the enhancements that are at issue, he's advising them that under the 3553A factors, after hearing argument and after hearing elocution, he will rule and he will impose a reasonable sentence based on those factors and to really focus their argument there. Certainly, had he said, I have my sentence decided, you can lay your record, but it's done, that would be, of course, a serious issue. And my understanding is he was providing guidance to them, and certainly the record shows that he did change his mind on one of the enhancements and was giving it all of the attention that it deserved, but I understand. Doesn't that itself demonstrate that this statement was not a reflection of what was going on in reality? And it seems hard to say that a judge could say, having not considered anything yet, I know that my sentence will be reasonable, and to expect us to say, okay, sure, he must have already known that he would make a reasonable sentence. That seems like a bit of a I certainly see the concern. I read it as him saying that his approach will be one to focus on those factors in coming to a reasonable sentence, but I understand there is a concern. And you agree that it can't insulate? Certainly, Your Honor. I mean, the way he did it cannot insulate his sentencing decision. I certainly understand, Your Honor, and I think because he did not clearly err in the enhancements, that is the argument that the government is focused on here. So how do we stop the district judge from making his keen statements before he even calculates the guideline sentence? How do we do that then? Well, Your Honor, I know actually in United States v. Delgado, this court did include a footnote where because they did not need to reach a keen finding, because the district court judge there had not clearly erred, the court did say the better practice if we reverse based on you can't do it before you calculate the guidelines, then that would be a little more effective, wouldn't it? Then you shouldn't do it. Your Honor, I think we don't reach that unless he did clearly err on the enhancements. But I do think a footnote similar to the one in United States v. Delgado about the best practice in the Eleventh Circuit would emphasize this note that this is how it should be done. Gotcha. Thank you. Thank you, Your Honor. Your Honor, if you have no further questions, the government rests on its brief. All right. Ms. Budrotti, you've reserved some time for rebuttal. Thank you, Your Honor. I first want to address the standard of review that applies. Again, pointing you to United States v. Williams. This is also a quote. The district court's application of 3B1.1 to determine if that person is a participant is a question of law that the court reviews de novo. And so I believe this court's review as to this question is de novo. And with regard to why these individuals are not participants as that word is defined under the guidelines, the government propounded the testimony of one of these individuals and his testimony was that he did not know. He thought the money was Mr. Bindernoth's and he believed it be to be being sent to Nigeria to help Mr. Bindernoth's family. And the aunt that testified similarly, she noted that she was told that he needed help sending money to his girlfriend who was in a hospital in Nigeria. The key point being no one knew anything about the money laundering scheme that Mr. Bindernoth was allegedly involved in. There are there any other cases that explain a different standard of review? Because I will confess I'm not understanding why the standard of review for that guideline would be different than the ordinary, which is, of course, legal decisions de novo and issues of fact clearly erroneous. It sounds it sounds like that's a little bit different to me. What is something I'm missing? No, the de novo review for whether someone is a participant. That seems more like a factual issue to me. It's more about application of the guideline, which I think is in line with this court's precedent about when guideline errors are deserving of de novo review versus abuse of discretion are clearly erroneous. We're not challenging the factual determinations. You know, the government's propounding like there are 20 people. It was the aunt. It was a friend like those aren't what's being challenged. What's being challenged is the application of those facts to a legal definition to the actual guideline. And because that's a legal question, that's why it's deserving of de novo review by this court, because it's a determination of whether the actual guideline itself is applicable to these factual circumstances. It's not really equivalent with what the facts actually were. But do you think the specific question of whether someone is a participant is a question of law? Yes, at least under and under this court's precedent and under the precedent that applies to the application of the guidelines overall. And if I may, very quickly, the government sort of said, I think, that they didn't even refer to these individuals as victims at the time of sentencing. And even as late as their 3553 argument in the sentencing transcript on page 45, they note that he victimized members of his community. There's just no quibbling with the fact that even the government conceived of these individuals not as participants, not as criminally culpable individuals, but as victims. And because of that, it was inappropriate by law and under the very definition of the guideline to apply this enhancement. Thank you. Thank you, counsel.",
            stt_status=Audio.STT_COMPLETE,
        )

        cls.open_ai_api_returned_dict = {
            "text": "Good morning, Camille Fenton, Federal Defenders, on behalf of Mr. Campos.",
            "task": "transcribe",
            "language": "english",
            "duration": 6.15,
            "segments": [
                {
                    "id": 0,
                    "end": 6.159999847412109,
                    "seek": 0,
                    "text": "Good morning, Camille Fenton, Federal Defenders, on behalf of Mr. Campos.",
                    "start": 1.5399999618530273,
                    "tokens": [
                        50364,
                        2205,
                        2446,
                        11,
                        6886,
                        3409,
                        479,
                        317,
                        266,
                        11,
                        12380,
                        9548,
                        16292,
                        11,
                        322,
                        9490,
                        295,
                        2221,
                        13,
                        9189,
                        329,
                        13,
                        50652,
                    ],
                    "avg_logprob": -0.2830151319503784,
                    "temperature": 0.0,
                    "no_speech_prob": 0.02627764642238617,
                    "compression_ratio": 1.4403291940689087,
                },
            ],
            "words": [
                {
                    "end": 2.059999942779541,
                    "word": "Good",
                    "start": 1.5399999618530273,
                },
                {
                    "end": 2.299999952316284,
                    "word": "morning",
                    "start": 2.059999942779541,
                },
                {
                    "end": 2.6600000858306885,
                    "word": "Camille",
                    "start": 2.4200000762939453,
                },
                {
                    "end": 2.9800000190734863,
                    "word": "Fenton",
                    "start": 2.6600000858306885,
                },
                {
                    "end": 3.380000114440918,
                    "word": "Federal",
                    "start": 3.140000104904175,
                },
                {
                    "end": 3.759999990463257,
                    "word": "Defenders",
                    "start": 3.380000114440918,
                },
                {
                    "end": 4.159999847412109,
                    "word": "on",
                    "start": 3.9000000953674316,
                },
                {
                    "end": 4.380000114440918,
                    "word": "behalf",
                    "start": 4.159999847412109,
                },
                {
                    "end": 4.539999961853027,
                    "word": "of",
                    "start": 4.380000114440918,
                },
                {
                    "end": 4.800000190734863,
                    "word": "Mr",
                    "start": 4.539999961853027,
                },
                {
                    "end": 5.320000171661377,
                    "word": "Campos",
                    "start": 5.059999942779541,
                },
            ],
        }

        class OpenAITranscription:
            def to_dict(self):
                return cls.open_ai_api_returned_dict

        cls.OpenAITranscriptionClass = OpenAITranscription

    def test_audio_file_validation(self) -> None:
        """Can we validate audio files existance and size for OpenAI API use?"""
        can_be_processed = audio_can_be_processed_by_open_ai_api(
            self.audio_without_local_path_mp3
        )
        self.assertFalse(
            can_be_processed,
            "Audio object without local_path_mp3 passed as valid",
        )
        self.audio_without_local_path_mp3.refresh_from_db()
        self.assertEqual(
            self.audio_without_local_path_mp3.stt_status,
            Audio.STT_NO_FILE,
            "status was not updated to STT_NO_FILE",
        )

        can_be_processed = audio_can_be_processed_by_open_ai_api(
            self.audio_bigger_than_limit_duration
        )
        self.assertFalse(
            can_be_processed,
            "Longer than allowed audio file passed as valid",
        )
        self.audio_bigger_than_limit_duration.refresh_from_db()
        self.assertEqual(
            self.audio_bigger_than_limit_duration.stt_status,
            Audio.STT_FILE_TOO_BIG,
            "status was not updated to STT_FILE_TOO_BIG",
        )

        self.assertTrue(
            audio_can_be_processed_by_open_ai_api(self.audio_1),
            "Valid audio file was skipped",
        )
        self.assertTrue(
            audio_can_be_processed_by_open_ai_api(self.audio_to_be_retried),
            "Valid audio file was skipped",
        )

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "123"}, clear=True)
    def test_successful_api_call(self) -> None:
        """Is Audio object updated and AudioTranscriptMetadata created correctly?"""
        audio = self.audio_1

        with mock.patch(
            "openai.resources.audio.transcriptions.Transcriptions.create"
        ) as patched_transcription:
            patched_transcription.return_value = (
                self.OpenAITranscriptionClass()
            )
            transcribe_from_open_ai_api(audio_pk=audio.pk)

        audio.refresh_from_db()
        self.assertEqual(
            audio.stt_status,
            Audio.STT_COMPLETE,
            "Audio.stt_status is not Audio.STT_COMPLETED",
        )
        self.assertEqual(
            audio.stt_source,
            Audio.STT_OPENAI_WHISPER,
            "Audio.stt_source is not Audio.STT_OPENAI_WHISPER",
        )

        transcription = self.open_ai_api_returned_dict
        self.assertEqual(
            audio.duration,
            ceil(transcription["duration"]),
            "Audio.duration was not updated",
        )
        self.assertEqual(
            audio.stt_transcript,
            transcription["text"],
            "Audio.stt_transcript was not updated",
        )
        queryset = AudioTranscriptionMetadata.objects.filter(audio=audio)
        self.assertTrue(
            queryset.exists(),
            "AudioTranscriptionMetadata was not created",
        )
        metadata = queryset[0]
        self.assertEqual(
            metadata.metadata["words"][0]["word"],
            transcription["words"][0]["word"],
            "AudioTranscriptionMetadata[words][0] not as expected",
        )
        self.assertEqual(
            metadata.metadata["segments"][0]["text"],
            transcription["segments"][0]["text"],
            "AudioTranscriptionMetadata[segments][0] not as expected",
        )

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "123"}, clear=True)
    def test_failure_status_update(self) -> None:
        """Is Audio.stt_status updated correctly on failure?"""
        audio = self.audio_1

        with mock.patch(
            "openai.resources.audio.transcriptions.Transcriptions.create"
        ) as patched_transcription:
            mock_response = MockResponse(422, content="")
            setattr(mock_response, "request", {})
            setattr(mock_response, "headers", {"x-request-id": "1"})
            patched_transcription.side_effect = (
                openai.UnprocessableEntityError(
                    message="Test OpenAI API UnprocessableEntityError",
                    response=mock_response,
                    body="",
                )
            )
            transcribe_from_open_ai_api(audio_pk=audio.pk)

        audio.refresh_from_db()
        self.assertEqual(
            audio.stt_status,
            Audio.STT_FAILED,
            "Audio.stt_status is not Audio.STT_FAILED",
        )

    def test_hallucination_detection(self):
        """Can we detect the most obvious hallucinations?"""
        self.assertTrue(
            transcription_was_hallucinated(
                self.transcripted_audio_hallucination
            )
        )
        self.assertFalse(
            transcription_was_hallucinated(
                self.transcripted_audio_not_hallucinated
            )
        )
