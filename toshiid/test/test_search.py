import os
import names as namegen
from tornado.escape import json_decode, json_encode
from tornado.testing import gen_test

from toshiid.app import urls
from toshi.test.base import AsyncHandlerTest
from toshi.test.database import requires_database
from toshi.ethereum.utils import data_encoder, private_key_to_address

from urllib.parse import quote_plus, quote as quote_arg

from toshiid.test.test_user import TEST_PRIVATE_KEY, TEST_ADDRESS, TEST_PAYMENT_ADDRESS

class SearchUserHandlerTest(AsyncHandlerTest):

    def setUp(self):
        super().setUp(extraconf={'general': {'apps_dont_require_websocket': True}})

    def get_urls(self):
        return urls

    def fetch(self, url, **kwargs):
        return super(SearchUserHandlerTest, self).fetch(url, **kwargs)

    def get_url(self, path):
        path = "/v1{}".format(path)
        return super().get_url(path)

    @gen_test
    @requires_database
    async def test_username_query(self):

        username = "bobsmith"
        positive_query = 'bobsm'
        negative_query = 'nancy'

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id) VALUES ($1, $2)", username, TEST_ADDRESS)

        resp = await self.fetch("/search/user?query={}".format(positive_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 1)

        # ensure we got a tracking event
        self.assertEqual((await self.next_tracking_event())[0], None)

        resp = await self.fetch("/search/user?query={}".format(negative_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

        # ensure we got a tracking event
        self.assertEqual((await self.next_tracking_event())[0], None)

    @gen_test
    @requires_database
    async def test_invalid_username_query(self):

        username = "bobsmith"
        invalid_query = quote_plus('!@#$')

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id) VALUES ($1, $2)", username, TEST_ADDRESS)

        resp = await self.fetch("/search/user?query={}".format(invalid_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

    @gen_test
    @requires_database
    async def test_username_query_sql_inject_attampt(self):

        username = "bobsmith"
        inject_attempt = quote_plus("x'; delete from users; select * from users")

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id) VALUES ($1, $2)", username, TEST_ADDRESS)

        resp = await self.fetch("/search/user?query={}".format(inject_attempt), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

        async with self.pool.acquire() as con:
            row = await con.fetchrow("SELECT COUNT(*) AS count FROM users")

        self.assertEqual(row['count'], 1)

    @gen_test
    @requires_database
    async def test_bad_limit_and_offset(self):

        positive_query = 'bobsm'

        resp = await self.fetch("/search/user?query={}&offset=x".format(positive_query), method="GET")
        self.assertEqual(resp.code, 400)

        resp = await self.fetch("/search/user?query={}&limit=x".format(positive_query), method="GET")
        self.assertEqual(resp.code, 400)

    @gen_test
    @requires_database
    async def test_limit_and_offset(self):

        username = "bobsmith"
        address = int(TEST_ADDRESS[2:], 16)
        num_of_users = 170

        async with self.pool.acquire() as con:
            # creates a bunch of users with numbering suffix to test limit and offset
            # insert users in reverse order to assure that search results are returned in alphabetical order
            for i in range(num_of_users - 1, -1, -1):
                await con.execute("INSERT INTO users (username, toshi_id) VALUES ($1, $2)",
                                  # make sure the suffix is always the same length to ensure it's easy to match alphabetical ordering
                                  "{0}{1:0{2}}".format(username, i, len(str(num_of_users))),
                                  # makes sure every user has a different eth address
                                  "{0:#0{1}x}".format(address + i, 42))

        positive_query = 'bobsm'
        test_limit = 30

        for i in range(0, num_of_users, test_limit):
            resp = await self.fetch("/search/user?query={}&limit={}&offset={}".format(positive_query, test_limit, i), method="GET")
            self.assertEqual(resp.code, 200)
            body = json_decode(resp.body)
            self.assertEqual(len(body['results']), min(i + test_limit, num_of_users) - i)
            j = i
            for res in body['results']:
                self.assertEqual(res['username'], "{0}{1:0{2}}".format(username, j, len(str(num_of_users))))
                j += 1

    @gen_test
    @requires_database
    async def test_only_apps_query(self):

        data_encoder, private_key_to_address
        users = [
            ('bob{}'.format(i), private_key_to_address(data_encoder(os.urandom(32))), False)
            for i in range(6)
        ]
        bots = [
            ('bot{}'.format(i), private_key_to_address(data_encoder(os.urandom(32))), True)
            for i in range(4)
        ]

        async with self.pool.acquire() as con:
            for args in users + bots:
                await con.execute("INSERT INTO users (username, toshi_id, is_app) VALUES ($1, $2, $3)", *args)

        resp = await self.fetch("/search/user?query=bo", method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 10)

        resp = await self.fetch("/search/user?query=bo&apps=false", method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 6)

        resp = await self.fetch("/search/user?query=bo&apps=true", method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 4)

    @gen_test
    @requires_database
    async def test_name_query(self):

        username = "user231"
        name = "Bobby"
        positive_query = 'bob'
        negative_query = 'nancy'

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id, name) VALUES ($1, $2, $3)",
                              username, TEST_ADDRESS, name)

        resp = await self.fetch("/search/user?query={}".format(positive_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 1)

        resp = await self.fetch("/search/user?query={}".format(negative_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

    # def get_app(self):
    #     self._config['database'] = {'dsn': 'postgresql://toshi@127.0.0.1/toshi-id'}
    #     app = super().get_app()
    #     self.pool = app.connection_pool
    #     return app

    @gen_test(timeout=300)
    @requires_database
    async def test_fulltextsearch(self):
        no_of_users_to_generate = 100
        insert_vals = [(private_key_to_address(os.urandom(32)), "user0", "Bob Smith")]
        some_bobs = False
        for i in range(1, no_of_users_to_generate):
            key = os.urandom(32)
            while True:
                name = namegen.get_full_name()
                # make sure we never generate any user's called bob
                if 'Bob' in name or 'bob' in name:
                    continue
                break
            # give ten of the users a 'bob##' username
            if i % (no_of_users_to_generate / 10) == 0:
                some_bobs = True
                username = 'bob{}'.format(i)
            else:
                username = 'user{}'.format(i)
            #resp = await self.fetch_signed(
            #    "/user", method="POST", signing_key=key,
            #    body=body)
            #self.assertEqual(resp.code, 200)
            insert_vals.append((private_key_to_address(key), username, name))
        async with self.pool.acquire() as con:
            await con.executemany(
                "INSERT INTO users (toshi_id, username, name) VALUES ($1, $2, $3)",
                insert_vals)
            count = await con.fetchrow("SELECT count(*) FROM users")
            bobcount = await con.fetchrow("SELECT count(*) FROM users where username ilike 'bob%'")
        self.assertTrue(count['count'] > 0)
        self.assertTrue(bobcount['count'] > 0)
        self.assertTrue(some_bobs)
        resp = await self.fetch("/search/user?query=bob", method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertTrue(len(results) > 1)
        # make sure that name is prefered over username
        self.assertEqual(results[0]['name'], "Bob Smith")
        self.assertTrue(results[1]['username'].startswith("bob"))

    @gen_test
    @requires_database
    async def test_payment_address_search(self):

        username = "user231"
        name = "Bobby"

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id, name, payment_address) VALUES ($1, $2, $3, $4)",
                              username, TEST_ADDRESS, name, TEST_PAYMENT_ADDRESS)

        # test simple lookup
        resp = await self.fetch("/search/user?payment_address={}".format(TEST_PAYMENT_ADDRESS), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 1)

        # test query + payment address
        resp = await self.fetch("/search/user?query={}&payment_address={}".format("user", TEST_PAYMENT_ADDRESS), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 1)

        # test no matches
        resp = await self.fetch("/search/user?payment_address={}".format(TEST_ADDRESS), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

        # test no matches due to name query failing
        resp = await self.fetch("/search/user?query={}&payment_address={}".format("nomatch", TEST_PAYMENT_ADDRESS), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

    @gen_test(timeout=30)
    @requires_database
    async def test_search_order_by_reputation(self):
        no_of_users_to_generate = 7
        insert_vals = []
        for i in range(0, no_of_users_to_generate):
            key = os.urandom(32)
            name = "John Smith"
            username = 'johnsmith{}'.format(i)
            insert_vals.append((private_key_to_address(key), username, name,
                                (i / (no_of_users_to_generate - 1)) * 5.0, 10))
        for j in range(i + 1, i + 4):
            key = os.urandom(32)
            name = "John Smith"
            username = 'johnsmith{}'.format(j)
            insert_vals.append((private_key_to_address(key), username, name,
                                (i / (no_of_users_to_generate - 1)) * 5.0, j))
        # add some users with no score to make sure
        # users who haven't been reviewed appear last
        for k in range(j + 1, j + 2):
            key = os.urandom(32)
            username = 'johnsmith{}'.format(k)
            insert_vals.append((private_key_to_address(key), username, name, None, 0))
        async with self.pool.acquire() as con:
            await con.executemany(
                "INSERT INTO users (toshi_id, username, name, reputation_score, review_count) VALUES ($1, $2, $3, $4, $5)",
                insert_vals)
        resp = await self.fetch("/search/user?query=Smith&limit={}".format(k + 1), method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertEqual(len(results), k + 1)
        # make sure that the highest rated "Smith" is first
        previous_rating = 5.1
        previous_count = None
        for user in results:
            rep = 2.01 if user['reputation_score'] is None else user['reputation_score']
            self.assertLessEqual(rep, previous_rating)
            if rep == previous_rating:
                self.assertLessEqual(user['review_count'], previous_count)
            previous_count = user['review_count']
            previous_rating = rep

    @gen_test
    @requires_database
    async def test_underscore_username_query(self):

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, name, toshi_id) VALUES ($1, $2, $3)",
                              "wager_weight", "Wager Weight", "0x0000000000000000000000000000000000000001")
            await con.execute("INSERT INTO users (username, name, toshi_id) VALUES ($1, $2, $3)",
                              "bob_smith", "Robert", "0x0000000000000000000000000000000000000002")
            await con.execute("INSERT INTO users (username, name, toshi_id) VALUES ($1, $2, $3)",
                              "bob_jack", "Jackie", "0x0000000000000000000000000000000000000003")
            await con.execute("INSERT INTO users (username, name, toshi_id) VALUES ($1, $2, $3)",
                              "user1234", "user1234", "0x0000000000000000000000000000000000000004")

        for positive_query in ["wager", "wager_we", "wager_weight", "bob_smi"]:

            resp = await self.fetch("/search/user?query={}".format(positive_query), method="GET")
            self.assertEqual(resp.code, 200)
            body = json_decode(resp.body)
            self.assertEqual(len(body['results']), 1, "Failed to get match for search query: {}".format(positive_query))

        for negative_query in ["wager_foo", "bob_bar", "1234", "bobsmith"]:

            resp = await self.fetch("/search/user?query={}".format(negative_query), method="GET")
            self.assertEqual(resp.code, 200)
            body = json_decode(resp.body)
            self.assertEqual(len(body['results']), 0, "got unexpected match for search query: {}".format(negative_query))

    @gen_test(timeout=30)
    @requires_database
    async def test_search_order_by_reputation_without_query(self):
        no_of_users_to_generate = 20
        insert_vals = []
        for i in range(0, no_of_users_to_generate):
            key = os.urandom(32)
            name = namegen.get_full_name()
            username = name.lower().replace(' ', '')
            insert_vals.append((private_key_to_address(key), username, name,
                                (i / (no_of_users_to_generate - 1)) * 5.0, 10,
                                True if i % 2 == 0 else False))
        for j in range(i + 1, i + 4):
            key = os.urandom(32)
            name = namegen.get_full_name()
            username = name.lower().replace(' ', '')
            insert_vals.append((private_key_to_address(key), username, name, (i / (no_of_users_to_generate - 1)) * 5.0, j, True if j % 2 == 0 else False))
        # add some users with no score to make sure
        # users who haven't been reviewed appear last
        for k in range(j + 1, j + 7):
            key = os.urandom(32)
            name = namegen.get_full_name()
            username = name.lower().replace(' ', '')
            insert_vals.append((private_key_to_address(key), username, name,
                                None, 0,
                                True if k % 2 == 0 else False))
        async with self.pool.acquire() as con:
            await con.executemany(
                "INSERT INTO users (toshi_id, username, name, reputation_score, review_count, is_public) VALUES ($1, $2, $3, $4, $5, $6)",
                insert_vals)
        resp = await self.fetch("/search/user?top=true&limit={}".format(k + 1), method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertEqual(len(results), k + 1)
        # make sure that the highest rated is first
        previous_rating = 5.1
        previous_count = None
        for user in results:
            rep = 2.01 if user['reputation_score'] is None else user['reputation_score']
            self.assertLessEqual(rep, previous_rating)
            if rep == previous_rating:
                self.assertLessEqual(user['review_count'], previous_count)
            previous_count = user['review_count']
            previous_rating = rep

        # check public search
        resp = await self.fetch("/search/user?top=true&public=true&limit={}".format(k + 1), method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertEqual(len(results), (k + (1 if k % 2 == 1 else 2)) // 2)
        # make sure that the highest rated is first
        previous_rating = 5.1
        previous_count = None
        for user in results:
            self.assertTrue(user['public'])
            rep = 2.01 if user['reputation_score'] is None else user['reputation_score']
            self.assertLessEqual(rep, previous_rating)
            if rep == previous_rating:
                self.assertLessEqual(user['review_count'], previous_count)
            previous_count = user['review_count']
            previous_rating = rep

    @gen_test(timeout=30)
    @requires_database
    async def test_apps_vs_public(self):
        """Make sure if something is marked as being an app it doesn't show up
        in the public list even if marked with public"""

        no_of_users_to_generate = 20
        insert_vals = []
        for i in range(0, no_of_users_to_generate):
            key = os.urandom(32)
            name = namegen.get_full_name()
            username = name.lower().replace(' ', '')
            insert_vals.append((private_key_to_address(key), username, name,
                                (i / (no_of_users_to_generate - 1)) * 5.0, 10,
                                True, True if i % 2 == 0 else False))

        async with self.pool.acquire() as con:
            await con.executemany(
                "INSERT INTO users (toshi_id, username, name, reputation_score, review_count, is_public, is_app) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                insert_vals)

        resp = await self.fetch("/search/user?limit={}".format(i + 1), method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertEqual(len(results), no_of_users_to_generate)

        resp = await self.fetch("/search/user?public=true&limit={}".format(i + 1), method="GET")
        self.assertEqual(resp.code, 200)
        results = json_decode(resp.body)['results']
        self.assertEqual(len(results), (i + (1 if i % 2 == 1 else 2)) // 2)

    @gen_test
    @requires_database
    async def test_inactive_username_query(self):

        username = "bobsmith"
        positive_query = 'bobsm'

        async with self.pool.acquire() as con:
            await con.execute("INSERT INTO users (username, toshi_id, active) VALUES ($1, $2, false)", username, TEST_ADDRESS)

        resp = await self.fetch("/search/user?query={}".format(positive_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 0)

        resp = await self.fetch_signed("/user", signing_key=TEST_PRIVATE_KEY, method="PUT", body={
            "payment_address": TEST_ADDRESS
        })
        self.assertResponseCodeEqual(resp, 200)

        resp = await self.fetch("/search/user?query={}".format(positive_query), method="GET")
        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertEqual(len(body['results']), 1)

    @gen_test(timeout=10)
    @requires_database
    async def test_contact_list_query(self):

        total_users = 10000
        # NOTE: this seems to be the limit for query string length
        # that the server will accept
        query_users = 1255

        users = [(data_encoder(os.urandom(20)), hex(i)) for i in range(total_users)]
        bad_users = [
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "0xcccccccccccccccccccccccccccccccccccccccc"
        ]
        bad_users.extend(user[0] for user in users[:3])

        async with self.pool.acquire() as con:
            await con.executemany("INSERT INTO users (toshi_id, username, active) VALUES ($1, $2, false)",
                                  users)

        resp = await self.fetch("/search/user?{}".format("&".join("toshi_id={}".format(toshi_id) for toshi_id, _ in users[:query_users])))

        self.assertEqual(resp.code, 200)
        body = json_decode(resp.body)
        self.assertIn('results', body)
        self.assertEqual(len(body['results']), query_users)
        for u, r in zip(users, body['results']):
            self.assertEqual(u[0], r['toshi_id'])

        resp = await self.fetch("/search/user?{}".format("&".join("toshi_id={}".format(toshi_id) for toshi_id in bad_users)))
        body = json_decode(resp.body)
        self.assertIn('results', body)
        self.assertEqual(len(body['results']), 3)

        # make sure we're safe from injection
        inject = "0')) AS a (id) ON u.toshi_id = a.id; DELETE FROM users; SELECT u.* FROM users u JOIN ( VALUES ('0x0000000000000000000000000000000000000000"
        resp = await self.fetch("/search/user?toshi_id={}".format(quote_arg(inject)))
        self.assertEqual(resp.code, 400)
