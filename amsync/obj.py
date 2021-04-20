from __future__ import annotations

from typing import Any, Callable, NoReturn, Dict
from pathlib import Path
from asyncio import gather
from platform import system
from subprocess import run
from contextlib import suppress
from unicodedata import normalize

from magic import from_buffer
from ujson import dumps, loads, dump
from aiohttp import request
from pybase64 import b64encode

from .enum import MediaType
from .exceptions import (
    SmallReasonForBan,
    InvalidFileType
)


headers: dict[str, str] = {'NDCDEVICEID': '0146BD6CF162E40F7449AFF316BA524DDDE1A1C4E6D99A553F3472EC3F4CB2F6A9ED05E5100492DC76'}
actual_com:  str | None = None
actual_chat: str | None = None
bot_id:      str | None = None
API = 'https://service.narvii.com/api/v1/'

Req_json = Dict[str, Any]


def clear() -> None:
    run('cls' if system() == 'Windows' else 'clear', shell=True)

def exist(
    d:       Req_json,
    k:       str,
    convert: Any | None = None
) -> Any | None:

    with suppress(KeyError):
        if convert:
            tmp = convert(d[k])
            return tmp if tmp else None
        return d[k]

def fix_ascii(s) -> str:
    return normalize('NFKD', s).encode('ASCII', 'ignore').decode().strip()


def on_limit(
    obj:   list[Any],
    limit: int
) -> bool:
    return limit and len(obj) >= limit


async def upload_media(file):
    return (
        await _req(
            'post',
            '/g/s/media/upload',
            data=await File.get(file),
            need_dumps=False,
        )
    )['mediaValue']

async def _req(
    method:     str,
    url:        str,
    *,
    data:       dict[str, Any] | None = None,
    need_dumps: bool                  = True,
    return_:    str                   = 'json',
) -> Req_json | str | bytes:

    async def get_return(res):
        if return_ == 'json':
            return await res.json(loads=loads)
        if return_ == 'text':
            return await res.text()
        if return_ == 'file':
            return await res.read()
        raise Exception(f'Invalid return "{return_}"')

    async with request(
        method,
        API + url,
        data=dumps(data) if need_dumps else data,
        headers=headers,
        raise_for_status=True,
    ) as _req:
        return await get_return(_req)


class Message:
    __slots__ = (
        'author',
        'chat',
        'com',
        'extensions',
        'file_link',
        'has_mention',
        'icon',
        'id',
        'media_type',
        'mentioned_users',
        'nickname',
        'text',
        'type',
        'uid',
    )

    def from_ws(self, j: Req_json) -> Message:
        _cm: dict[str, Any] = j['chatMessage']

        global actual_chat, actual_com
        self.chat: str | None = exist(_cm, 'threadId', str)
        self.com:  str | None = exist(j, 'ndcId', str)

        actual_chat = self.chat
        actual_com = self.com

        self.extensions:  dict[str, Any] | None = exist(_cm, 'extensions')
        self.file_link:   str | None            = exist(_cm, 'mediaValue')
        self.has_mention: bool                  = (
                                                True
                                                if exist(self.extensions, 'mentionedArray')
                                                else False
                                            )

        self.icon:            str | None       = exist(_cm['author'], 'icon') if 'author' in _cm else None
        self.id:              str | None       = exist(_cm, 'messageId')
        self.media_type:      str | None       = exist(_cm, 'mediaType')
        self.mentioned_users: list[str] | None = (
                                                [u['uid']
                                                for u in self.extensions['mentionedArray']]
                                                if self.has_mention
                                                else None
                                            )

        self.nickname: str | None = exist(_cm['author'], 'nickname') if 'author' in _cm else None
        self.text:     str | None = exist(_cm, 'content')
        self.type:     str | None = exist(_cm, 'type')
        self.uid:      str | None = exist(_cm, 'uid')

        return self

    def from_chat(self, j: Req_json) -> Message:
        self.author:      User | None           = User(exist(j, 'author'))
        self.chat:        str  | None           = exist(j, 'threadId')
        self.extensions:  dict[str, Any] | None = exist(j, 'extensions')
        self.has_mention: bool                  = (
                                                True
                                                if exist(self.extensions, 'mentionedArray')
                                                else False
                                            )
        self.id:              str | None        = exist(j, 'messageId')
        self.mentioned_users: list[str] | None  = (
                                                [u['uid']
                                                for u in j['extensions']['mentionedArray']]
                                                if self.has_mention
                                                else None
                                            )
        self.text: str | None = exist(j, 'content')
        self.type: str | None = exist(j, 'type')
        return self

    class _CreateData:
        async def msg(type_, msgs):
            return [{'type': type_, 'content': i} for i in msgs]

        async def file(files):
            return [await File().process(i) for i in files]

        async def embed(embed: Embed):
            if embed.image:
                embed.image = [[100, await upload_media(embed.image), None]]
            return [
                {
                    'content': embed.msg_text,
                    'attachedObject': {
                        'link':      embed.link,
                        'title':     embed.title,
                        'content':   embed.text,
                        'mediaList': embed.image,
                    },
                }
            ]

    async def send(
        self,
        *msgs: list[str],
        files: str | list[str] | None = None,
        type_: int | None             = 0,
        embed: Embed | None           = None,
        com:   str | None             = None,
        chat:  str | None             = None,
    ) -> list[Req_json]:

        com = actual_com or com
        chat = actual_chat or chat
        files = [files] if files and not isinstance(files, (tuple, list)) else files

        if msgs:
            data = await self._CreateData.msg(type_, msgs)
        elif files:
            data = await self._CreateData.file(files)
        else:
            data = await self._CreateData.embed(embed)

        async def foo(i: msgs | files | list[Embed]) -> _req:
            return await _req(
                'post',
                f'x{com}/s/chat/thread/{chat}/message',
                data=i
            )

        return await gather(*[foo(i) for i in data])


class Embed:
    __slots__ = ('msg_text', 'title', 'text', 'link', 'image')

    def __init__(self, msg_text, title, text, link, image=None):
        self.msg_text = msg_text
        self.title = title
        self.text = text
        self.link = link
        self.image = image


class User:
    __slots__ = (
        'bio',
        'blogs_count',
        'com',
        'comments_count',
        'created_time',
        'followers_count',
        'following_count',
        'id',
        'im_following',
        'is_online',
        'level',
        'nickname',
        'posts_count',
        'reputation',
        'role',
        'visitors_count',
    )

    def __init__(self, j: Req_json | None = None):
        if j:
            self.bio             = exist(j, 'content')
            self.blogs_count     = exist(j, 'blogsCount')
            self.com             = exist(j, 'ndcId', str)
            self.comments_count  = exist(j, 'commentsCount')
            self.created_time    = exist(j, 'createdTime')
            self.followers_count = exist(j, 'membersCount')
            self.following_count = exist(j, 'joinedCount')
            self.im_following    = j['followingStatus'] == 1 if 'followingStatus' in j else None
            self.level           = exist(j, 'level')
            self.nickname        = exist(j, 'nickname')
            self.posts_count     = exist(j, 'postsCount')
            self.id              = exist(j, 'uid')
            self.reputation      = exist(j, 'reputation')
            self.role            = {0: 'member', 101: 'curator', 100: 'leader', 102: 'leader-agent'}[j['role']]
            self.visitors_count  = exist(j, 'visitoresCount')

    @classmethod
    async def search(
        cls, uids: str | list[str], com: str | None = None
    ) -> list[User]:

        com = actual_com or com
        uids = [uids] if not isinstance(uids, (list, tuple)) else uids

        async def foo(uid: str) -> User:
            return cls(
                (await _req('get', f'x{com}/s/user-profile/{uid}'))[
                    'userProfile'
                ]
            )

        return await gather(*[foo(uid) for uid in uids])

    async def ban(self, uid, *, reason, com=None):
        com = actual_com or com
        if len(reason.split()) < 3:
            raise SmallReasonForBan('Put a reason with at least three words')

        return await _req(
            'post',
            f'x{com}/s/user-profile/{uid}/ban',
            data={'reasonType': 200, 'note': {'content': reason}},
        )

    async def unban(self, uid, *, reason='', com=None):
        com = com or actual_com

        return await _req(
            'post',
            f'x{com}/s/user-profile/{uid}/unban',
            data={'note': {'content': reason}} if reason else None,
        )


class File:
    @staticmethod
    def type_(file):
        if isinstance(file, str) and file.startswith('http'):
            return MediaType.LINK

        if isinstance(file, bytes):
            return MediaType.BYTES

        return MediaType.PATH

    @staticmethod
    async def get(file: str) -> bytes:
        type = File.type_(file)

        if type == MediaType.LINK:
            async with request('get', file) as res:
                return await res.read()

        if type == MediaType.BYTES:
            return file

        with open(file, 'rb') as f:
            return f.read()

    @staticmethod
    def b64(file_bytes: bytes) -> str:
        return b64encode(file_bytes).decode()

    async def process(self, file: str | bytes) -> dict[str, Any] | NoReturn:
        if (
            self.type_(file) not in (MediaType.LINK, MediaType.BYTES)
            and not Path(file).exists()
        ):
            raise FileNotFoundError(file)

        b = await self.get(file)

        # python-magic using at least the first 2048 bytes,
        # as less can produce incorrect identification
        #
        # https://github.com/ahupp/python-magic#usage
        type_ = from_buffer(b[:2048], mime=True).split('/')

        if type_[1] == 'gif':
                return {
                'mediaType': 100,
                'mediaUploadValue': self.b64(b),
                'mediaUploadValueContentType': 'image/gif',
                'mediaUhqEnabled': True,
            }

        if type_[0] == 'image':
            return {
                'mediaType': 100,
                'mediaUploadValue': self.b64(b),
                'mediaUhqEnabled': True,
            }

        if type_[0] == 'audio':
            return {
                'type': 2,
                'mediaType': 110,
                'mediaUploadValue': self.b64(b),
                'mediaUhqEnabled': True,
            }

        raise InvalidFileType(file if type_ != MediaType.BYTES else '')


class Chat:
    __slots__ = (
        'announcement',
        'bg',
        'can_send_coins',
        'co_hosts',
        'creator',
        'extensions',
        'icon',
        'id',
        'is_pinned',
        'is_private',
        'members_can_invite',
        'name',
        'text',
        'title',
        'view_only'
    )

    def __init__(self, j=None):
        if j:
            t = j['thread']
            self.extensions         = exist(t, 'extensions')

            self.announcement       = exist(self.extensions, 'announcement') or ''
            self.bg                 = exist(self.extensions, 'bm')[1] if 'bm' in self.extensions else None
            self.can_send_coins     = exist(t['tipInfo'], 'tippable') if 'tipInfo' in t else None
            self.co_hosts           = exist(self.extensions, 'coHost') or []
            self.creator            = exist(t['author'], 'uid')
            self.icon               = exist(t, 'icon')
            self.id                 = exist(t, 'threadId')
            self.is_pinned          = exist(t, 'isPinned')
            self.is_private         = exist(t, 'membersQuota') == 2
            self.members_can_invite = exist(t, 'membersCanInvite')
            self.name               = exist(t, 'title')
            self.text               = '' if exist(t, 'content') in ('None', None) else exist(t, 'content')
            self.view_only          = exist(self.extensions, 'viewOnly') or False

    @classmethod
    async def search(cls, com=None, chat=None):
        com = actual_com or com
        chat = actual_chat or chat

        return cls(await _req(
            'get',
            f'x{com}/s/chat/thread/{chat}'
        ))

    async def messages(
        self,
        *,
        check: Callable[[Message], bool] = lambda _: True,
        com:   str | None = None,
        chat:  str | None = None,
        start: int | None = None,
        end:   int | None = None,
    ) -> list[Message.from_chat]:

        com = actual_com or com
        chat = actual_chat or chat
        messages = []

        res = await _req(
            'get',
            f'x{com}/s/chat/thread/{chat}/message?v=2&pagingType=t&size=100',
        )
        token = res['paging']['nextPageToken']
        for msg_ in res['messageList']:
            if check(msg := Message().from_chat(msg_)):
                messages.append(msg)

        while True:
            res = await _req(
                'get',
                f'x{com}/s/chat/thread/{chat}/message?v=2&pagingType=t&pageToken={token}&size=100',
            )
            for msg in res['messageList']:
                if check(msg := Message().from_chat(msg)):
                    messages.append(msg)

            if on_limit(messages, end):
                break

            try:
                token = res['paging']['nextPageToken']
            except KeyError:
                break

        return messages[start:end]

    async def clear(
        self,
        msgs:  str | list[str] | None = None,
        check: Callable[[Message], bool] = lambda _: True,
        com:   str | None = None,
        chat:  str | None = None,
        start: int | None = None,
        end:   int | None = None,
    ) -> list[Req_json]:

        com = actual_com or com
        chat = actual_chat or chat
        msgs = (
            ([msgs] if not isinstance(msgs, (tuple, list)) else msgs)
            if msgs
            else [
                msg.id
                for msg in await self.messages(
                    check=check, com=com, chat=chat, start=start, end=end
                )
            ]
        )

        async def foo(msg):
            return await _req(
                'post',
                f'x{com}/s/chat/thread/{chat}/message/{msg}/admin',
                data={'adminOpName': 102},
            )

        return await gather(*[foo(msg) for msg in msgs])

    async def members(
        self,
        check: Callable[[Message], bool] = lambda _: True,
        com:   str | None = None,
        chat:  str | None = None,
        start: int | None = None,
        end:   int | None = None,
    ):
        com = actual_com or com
        chat = actual_chat or chat

        async def foo(i):
            res = await _req(
                'get',
                f'x{com}/s/chat/thread/{chat}/member?start={i}&size=100&type=default&cv=1.2',
            )
            return [
                i
                for i in [
                    User(i) for i in res['memberList'] if res['memberList']
                ]
                if check(i)
            ]

        members_count = (await _req('get', f'x{com}/s/chat/thread/{chat}'))[
            'thread'
        ]['membersCount']
        MAX_MEMBERS_COUNT_IN_CHAT = 1000
        return (
            await gather(
                *[
                    foo(i)
                    for i in range(0, MAX_MEMBERS_COUNT_IN_CHAT, 100)
                    if i <= members_count
                ]
            )
        )[0][start:end]

    async def join(self, chat: str, com: str | None = None):
        com = actual_com or com
        chat = [chat] if not isinstance(chat, (list, tuple)) else chat

        async def foo(i):
            return await _req(
                'post', f'x{com}/s/chat/thread/{i}/member/{bot_id}'
            )

        return await gather(*[foo(i) for i in chat])

    async def leave(self, chat: str, com: str | None = None):
        com = actual_com or com
        chat = [chat] if not isinstance(chat, (list, tuple)) else chat

        async def foo(i):
            return await _req(
                'delete', f'x{com}/s/chat/thread/{i}/member/{bot_id}'
            )

        return await gather(*[foo(i) for i in chat])

    async def save(self, filename=None):
        chat = await Chat.search()
        info = {
            'name': chat.name,
            'text': chat.text,
            'announcement': chat.announcement,

            'bg': chat.bg,
            'icon': chat.icon,

            'creator': chat.creator,
            'co-hosts': chat.co_hosts,

            'can-send-coins': chat.can_send_coins,
            'is-pinned': chat.is_pinned,
            'only-view': chat.view_only,

            'members': [i.id for i in await self.members()]
        }

        n = 0
        while Path(f'{n}.json').exists():
            n += 1
        with open(filename or f'{n}.json', 'w') as f:
            dump(info, f, indent=4, ensure_ascii=False, escape_forward_slashes=False)


class Community:
    @staticmethod
    async def chats(com=None, need_print=False, ignore_ascii=False):
        if not actual_com and not com:
            raise Exception('Enter a com or send a message in a chat')

        com = com or actual_com
        com = [com] if not isinstance(com, (list, tuple)) else com

        async def foo(i):
            res = await _req(
                'get', f'x{i}/s/chat/thread?type=public-all&start=0&size=100'
            )
            return {str(i): [Chat(i) for i in res['threadList']]}

        a = await gather(*[foo(i) for i in com])
        chats = {k: v for i in a for k, v in i.items()}

        if need_print:
            for i, e in chats.items():
                max_name = len(
                    max(
                        [
                            i.name if not ignore_ascii else fix_ascii(i.name)
                            for i in e
                        ],
                        key=len,
                    )
                )
                print(i)
                for n in e:
                    name = n.name if not ignore_ascii else fix_ascii(n.name)
                    a = max_name - len(name)
                    print(f"    {name} {' '*a}-> {n.id}")
                print()
        return chats


class My:
    @staticmethod
    async def chats(need_print=True, ignore_ascii=False):
        res = await _req('get', 'g/s/community/joined?v=1&start=0&size=50')
        coms = {str(i['ndcId']): [i['name'], []] for i in res['communityList']}

        async def foo(i):
            return await _req(
                'get', f'x{i}/s/chat/thread?type=joined-me&start=0&size=100'
            )

        chats = await gather(*[foo(i) for i in coms])

        for i in chats:
            for j in i['threadList']:
                com_id = str(j['ndcId'])
                chat_id = j['threadId']
                is_private_chat = j['membersQuota'] == 2
                chat_name = (
                    j['membersSummary'][1]['nickname']
                    if is_private_chat
                    else j['title']
                )

                coms[com_id][1].append(
                    (
                        chat_name if not ignore_ascii else fix_ascii(chat_name),
                        chat_id,
                    )
                )

        if need_print:
            for i, e in coms.items():
                max_name = (
                    len(max([i[0] for i in e[1]], key=len)) if e[1] else 0
                )
                print(f'{coms[i][0]} - {i}')
                for j in coms[i][1]:
                    a = (max_name - len(j[0])) + 1
                    print(f'    {j[0]} {" "*a}-> {j[1]}')
                print()

        return coms

    @staticmethod
    async def communities(need_print=True, ignore_ascii=False):
        res = await _req('get', f'g/s/community/joined?v=1&start=0&size=50')
        coms = {
            i['name']
            if not ignore_ascii
            else fix_ascii(i['name']): str(i['ndcId'])
            for i in res['communityList']
        }

        if need_print:
            max_name = len(max(coms.keys(), key=len))
            for i, e in coms.items():
                a = max_name - len(i)
                print(f'{i} {" "*a} -> {e}')

        return coms
