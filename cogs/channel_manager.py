import asyncio
import logging
import os
import random
import re
from operator import itemgetter

from discord import ChannelType, endpoints
from discord.ext import commands

from cogs.utils import checks
from cogs.utils.dataIO import dataIO
from red import send_cmd_help

default_server_vars = {
    'min_empty_channels': {
        'type': int,
        'value': 2
    }
}
logger = logging.getLogger("red.channel_manager")
logger.setLevel(logging.DEBUG)
class ChannelManager:


    def __init__(self, bot):
        logger.info('loading module')
        self.paused = False
        self.update_period = 10

        self.bot = bot
        self.data = None
        self.baseDataPath = "data/channel_manager"
        self.dataFilePath = os.path.join(self.baseDataPath,"data.json")
        logger.debug("attempting to load settings from {0}".format(self.dataFilePath))
        if not os.path.exists(self.baseDataPath):
            logger.debug("settings directory at path {0} doesn't exist, creating it")
            os.mkdir(self.baseDataPath)
        if not os.path.isfile(self.dataFilePath) \
                or not dataIO.is_valid_json(self.dataFilePath):
            logger.debug("settings file doesn't exits, creating new file with default settings")
            self.data = {}
            self.save_data()
        else:
            self.data = dataIO.load_json(self.dataFilePath)
        logger.debug("loaded settings file with data: {0}".format(self.data))

    def save_data(self):
        dataIO.save_json(self.dataFilePath, self.data)

    def get_channel_name_pattern(self, group_name):
        channel_name_pattern = re.compile(r'^'+re.escape(group_name)+r'\s+#(\d+)')
        return channel_name_pattern
    def get_channel_number_in_group(self, group_name, channel):
        pattern = self.get_channel_name_pattern(group_name)
        match = pattern.match(channel.name)
        if (match):
            try:
                return int(match.group(1))
            except ValueError:
                return None

    @commands.group(pass_context=True)
    @checks.mod_or_permissions()
    async def cm(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            return

    @cm.command(pass_context=True)
    async def showdata(self,ctx):
        await self.bot.say(self.data)

    @cm.command(pass_context=True)
    async def addchan(self, ctx, new_name: str):
        """This does stuff!"""

        #Your code will go here
        #all_chans = [(channel.server.name,channel.name,channel.type, channel.position) for channel in self.bot.get_all_channels()]
        server = ctx.message.server
        if (server is not None):
            msg = "trying to create channel with name {new_name}, on server {server}".format(new_name=new_name, server=server)
            await self.bot.say(msg)
            new_chan = await self.bot.create_channel(server = server, name=new_name, type=ChannelType.voice)
            await self.bot.say("created channel {0}".format(new_chan))
            #await self.bot.say(all_chans)
        else:
            self.bot.say("no server id")
    @cm.command(pass_context=True)
    async def listchans(self, ctx):
        all_chans = ctx.message.server.channels
        voice_chans = [channel for channel in all_chans if channel.type==ChannelType.voice]
        lines = ["{0.name} - {0.position}".format(channel) for channel in voice_chans]
        await self.bot.say("\n".join(lines))

    @cm.command(pass_context=True)
    async def move(self, ctx, name, position):
        chan = findByName(ctx.message.server.channels, name)
        if (chan is not None):
            await self.bot.say("moving channel '{0}' to position '{1}'".format(chan, position))
            edited_chan = await self.bot.edit_channel(chan,position=position)
            await self.bot.say("edited chan '{0}'".format(edited_chan))

    @cm.command(pass_context = True)
    async def addgroup(self, ctx, group_name):
        channel_groups = self.get_channel_groups(ctx.message.server)

        channel_groups[group_name] = True
        self.save_data()

        logger.debug('added channel group {0!r}'.format(group_name))
        await self.bot.say('added channel group {0!r}'.format(group_name))

    @cm.command(name='removegroup', pass_context = True)
    async def remove_group(self, ctx, group_name, delete):
        channel_groups = self.get_channel_groups(ctx.message.server)
        if group_name not in channel_groups:
            await self.bot.say('group {0!r} doesn\'t exist'.format(group_name))
        else:
            del channel_groups[group_name]
            self.save_data()
            await self.bot.say('removing group {0!r}'.format(group_name))
            if (delete=='true'):
                for channel in self.get_channels_for_group(ctx.message.server, group_name):
                    await self.bot.delete_channel(channel=channel)

    def create_channel_name(self, group_name, num):
        return '{group_name} #{num}'.format(group_name=group_name, num = num)

    async def create_group_channel(self, server, group_name, num):
        chan_name = self.create_channel_name(group_name, num)
        logger.info('group {0!r} had no channels, creating new channel with name {1!r}'.format(group_name, chan_name))
        await self.bot.create_channel(server=server, name=chan_name, type = ChannelType.voice)

    async def update_scheduler(self):
        while self == self.bot.get_cog('ChannelManager'):
            if not self.paused:
                for server_id in self.data.keys():
                    server = self.bot.get_server(server_id)
                    logger.debug("attempting to get server with id {0}, result: {1}".format(server_id, server))
                    if server:
                        await self.update_groups(server)
            await asyncio.sleep(self.update_period)


    @cm.command(name = 'pause', pass_context=True)
    async def pause_loop(self):
        self.paused = not self.paused
        await self.bot.say('updates are now {0!r}'.format(self.paused))

    @cm.command(pass_context = True)
    async def start(self):
        self.paused = False
        await self.bot.say('starting update loop')
        await self.update_loop()

    @cm.command(name = 'upd', pass_context = True)
    async def upd(self, ctx):
        await self.update_groups(ctx.message.server)

    async def update_groups(self, server):
        channel_groups = self.get_channel_groups(server)
        for group_name in channel_groups:
            await self.update_group(server, group_name)
        await self.fix_channel_positions(server)

    def get_channels_for_group(self, server, group_name):
        pattern = self.get_channel_name_pattern(group_name)
        group_chans = [channel for channel in server.channels
                        if channel.type==ChannelType.voice
                        and pattern.match(channel.name)
                       ]
        return group_chans

    async def update_group(self, server, group_name):
        pattern = self.get_channel_name_pattern(group_name)
        min_empty_channels = self.get_server_var(server, 'min_empty_channels')
        logger.debug('updating channel group {0!r}'.format(group_name))

        group_chans = self.get_channels_for_group(server, group_name)

        if not group_chans:
            #if there are no channels for this group - create one and exit
            await self.create_group_channel(server,group_name,1)
            return
        #create channels if needed
        chan_to_numbers = {}
        chan_numbers = []
        empty_chans = []
        for channel in group_chans:
            if not channel.voice_members:
                empty_chans.append(channel)

            match = pattern.match(channel.name)
            if match:
                num = int(match.group(1))
                chan_to_numbers[channel] = num
                chan_numbers.append(num)
        n_chans_to_create = max(0, min_empty_channels - len(empty_chans))
        if n_chans_to_create > 0:
            logger.info('group {0} has {1!r} empty channels, min_empty is {min_empty}, will create {n_chans_to_create!r} channels'.format(group_name, len(empty_chans), min_empty = min_empty_channels, n_chans_to_create=n_chans_to_create))
            free_nums = find_free_numbers(chan_numbers, n_chans_to_create)
            for i in range(0, n_chans_to_create):
                chan_name = self.create_channel_name(group_name, free_nums[i])
                await self.bot.create_channel(server = server, name=chan_name, type=ChannelType.voice)

        #check if we should and can remove some channels
        n_to_remove = len(empty_chans) - min_empty_channels
        if n_to_remove > 0:
            logger.info('group {group_name} has {n_empty!r} empty channels, will attempt to remove {n_to_remove!r} channels'.format(group_name=group_name,n_empty=len(empty_chans), n_to_remove=n_to_remove))
            #create a list of empty channels sorted by number, remove the highest numbered ones
            empty_channels_with_number = [{'channel':channel, 'num':chan_to_numbers[channel]} for channel in empty_chans]
            empty_channels_with_number.sort(key=itemgetter('num'))
            for idx, chan_dict in enumerate(empty_channels_with_number):
                if idx>=min_empty_channels:
                    logger.debug("removing channel {0.name}".format(chan_dict['channel']))
                    await self.bot.delete_channel(channel=chan_dict['channel'])


    def get_voice_channels(self, server):
        return [channel for channel in server.channels if channel.type == ChannelType.voice]

    async def fix_channel_positions(self, server):
        channel_groups = self.get_channel_groups(server)
        channels = self.get_voice_channels(server)
        channels.sort(key=lambda ch: ch.position)
        channels_original = list(channels)
        logger.debug("initial channel positions: {0}".format([ch.name for ch in channels]))
        group_regexes = {group: self.get_channel_name_pattern(group) for group in channel_groups}
        channels_by_group = {group: [] for group in channel_groups}
        group_anchors = {}
        for idx, channel in enumerate(list(channels)):
            for group, regex in group_regexes.items():
                chan_num = self.get_channel_number_in_group(group_name=group, channel=channel)
                if chan_num is not None:
                    if chan_num == 1:
                        group_anchors[channel] = group
                    elif chan_num != 1:
                        channels.remove(channel)
                        channels_by_group[group].append({'num': chan_num, 'channel': channel})
        logger.debug('channels by group: {0}'.format(channels_by_group))
        result_channels = []
        for channel in channels:
            if channel not in group_anchors:
                #a channel that's not in any group (else it'd have been picked up in earlier processing, leave it where it is
                result_channels.append(channel)
            if channel in group_anchors:
                result_channels.append(channel)
                #first channel in a group, append it where it was
                group = group_anchors[channel]
                #get all channels in that group and add them in order
                group_channels = channels_by_group[group]
                group_channels.sort(key = itemgetter('num'))
                for grp_channel in group_channels:
                    result_channels.append(grp_channel['channel'])
        logger.debug('final channel positions: {0}'.format([channel.name for channel in result_channels]))
        changes = False
        for i, channel in enumerate(result_channels):
            if channel != channels_original[i]:
                changes = True
                break
        if changes:
            logger.debug("moving channels")
            await self.move_channels(server,result_channels)
        else:
            logger.debug('no changes in channel order')

    def get_data_for_server_from_context(self, ctx):
        server = ctx.message.server
        return self.get_data_for_server(server)

    def get_data_for_server(self, server):
        #TODO: create a class to manage loading/saving data per server, with fields instead of using dict keys, handle saving sets
        if server.id not in self.data:
            self.data[server.id] = {}
            self.save_data()
        return self.data[server.id]

    @cm.command(name = 'get', pass_context = True)
    async def get_cmd(self, ctx, key):
        if key is None:
            await self.bot.say('available variables are: {0!r}'.format(default_server_vars.keys()))
        else:
            value = self.get_server_var(ctx.message.server, key)
            await self.bot.say('{0!r}: {1!r}', key, value)

    @cm.command(name = 'set', pass_context = True)
    async def set_cmd(self, ctx, key, value):
        try:
            server_data = self.get_data_for_server_from_context(ctx)
            if value == 'None':
                del server_data[key]
            else:
                parsed = default_server_vars[key]['type'](value)
                server_data[key] = parsed
            await self.bot.say('setting {0!r}: {1!r}'.format(key, value))
            self.save_data()
        except ValueError as e:
            await self.bot.say(e)
        except KeyError as e:
            await self.bot.say('unknown variable {0!r}'.format(key))

    @cm.command(name = 'movechans', pass_context = True)
    async def shuffle(self,ctx, method='sort'):
        logger.info('moving channels')
        server = ctx.message.server
        voice_chans = [channel for channel in server.channels if channel.type == ChannelType.voice]
        if method=='sort':
            logger.debug('sorting voice channels')
            result = sorted(voice_chans, key=lambda chan: chan.name)
        elif method=='random':
            logger.debug('randomizing voice channels')
            result = list(voice_chans)
            random.shuffle(result)
        #await self.move_chans(voice_chans, result)
        await self.move_channels(server, result)

    async def move_chans(self, orig, result):
        original_positions = {chan: chan.position for chan in orig}
        n_moved = 0
        for new_pos, channel in enumerate(result):
            orig_pos = original_positions[channel]
            if orig_pos != new_pos:
                n_moved = n_moved + 1
                await self.bot.move_channel(channel=channel, position=new_pos)
        logger.debug('moved {0}/{1} channels'.format(n_moved, len(result)))

    async def move_channels(self, server, channels):

        payload = [{'id': c.id, 'position': index} for index, c in enumerate(channels)]
        url = '{0}/{1.id}/channels'.format(endpoints.SERVERS, server)
        logger.debug('using url: {0}'.format(url))
        logger.debug('using payload: {0!r}'.format(payload))
        await self.bot.http.patch(url, json=payload, bucket="move_channel")

    def get_server_var(self, server, key):
        server_data = self.get_data_for_server(server)
        if key in server_data:
            return server_data[key]
        if key in default_server_vars:
            return default_server_vars[key]['value']
        else:
            return None

    def set_server_var(self, server, key, value):
        server_data = self.get_data_for_server(server)
        server_data[key] = value
        self.save_data()

    def get_channel_groups(self, server):
        data = self.get_data_for_server(server)
        if 'channelGroups' not in data:
            data['channelGroups'] = {}
            self.save_data()
        return data['channelGroups']

def find_free_numbers(numbers, n_to_find):
    free_numbers = []
    max_num = max(numbers)
    for i in range(1, max_num):
       if (i not in numbers):
           free_numbers.append(i)
    n_found = len(free_numbers)
    for i in range(0,n_to_find - n_found):
       free_numbers.append(max_num+i+1)

    return free_numbers

def findByName(channels, name):
    for channel in channels:
        if (channel.name==name):
            return channel

def setup(bot):
    cm = ChannelManager(bot)
    bot.add_cog(cm)
    bot.loop.create_task(cm.update_scheduler())
