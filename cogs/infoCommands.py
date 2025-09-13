import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import io
import gc

CONFIG_FILE = "info_channels.json"

class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "http://raw.thug4ff.com/info"
        self.generate_url = "http://profile.thug4ff.com/api/profile"
        self.session = aiohttp.ClientSession()
        self.config_data = self.load_config()
        self.cooldowns = {}

    def convert_unix_timestamp(self, timestamp: int) -> str:
        return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    def load_config(self):
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("global_settings", {})
                    loaded_config["global_settings"].setdefault("default_all_channels", False)
                    loaded_config["global_settings"].setdefault("default_cooldown", 30)
                    loaded_config["global_settings"].setdefault("default_daily_limit", 30)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}")
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving config: {e}")

    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            
            if not allowed_channels:
                return True
                
            return str(ctx.channel.id) in allowed_channels
        except Exception as e:
            print(f"Error checking channel permission: {e}")
            return False

    @commands.hybrid_command(name="info", description="Displays account and guild stats for a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply(" Invalid UID! It must:\n- Be only numbers\n- Have at least 6 digits", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send(" This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f" Please wait {remaining}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status == 404:
                        return await ctx.send(f" Player with UID `{uid}` not found.")
                    if response.status != 200:
                        return await ctx.send("API error. Try again later.")
                    data = await response.json()

            basic_info = data.get('basicInfo', {})
            captain_info = data.get('captainBasicInfo', {})
            clan_info = data.get('clanBasicInfo', {})
            credit_score_info = data.get('creditScoreInfo', {})
            social_info = data.get('socialInfo', {})

            # Create a beautiful embed
            embed = discord.Embed(
                title=f"🎮 {basic_info.get('nickname', 'Unknown Player')}'s Free Fire Stats",
                color=0x00ffaa,  # Teal color
                timestamp=datetime.now()
            )
            
            # Set thumbnail if available
            if basic_info.get('nickname'):
                embed.set_thumbnail(url="https://i.imgur.com/6eQEsZP.png")  # Free Fire icon
            
            # Account Basic Info
            embed.add_field(
                name="📋 ACCOUNT INFORMATION",
                value=f"**Name:** {basic_info.get('nickname', 'N/A')}\n"
                      f"**UID:** `{uid}`\n"
                      f"**Level:** {basic_info.get('level', 'N/A')}\n"
                      f"**Experience:** {basic_info.get('exp', 'N/A')}\n"
                      f"**Region:** {basic_info.get('region', 'N/A')}\n"
                      f"**Honor Score:** {credit_score_info.get('creditScore', 'N/A')}",
                inline=False
            )
            
            # Rank Information
            br_rank = f"{basic_info.get('rankingPoints', 'N/A')}" if basic_info.get('showBrRank') else "Not Ranked"
            cs_rank = f"{basic_info.get('csRankingPoints', 'N/A')}" if basic_info.get('showCsRank') else "Not Ranked"
            
            embed.add_field(
                name="🏆 RANK STATISTICS",
                value=f"**Battle Royale Rank:** {br_rank}\n"
                      f"**Clash Squad Rank:** {cs_rank}\n"
                      f"**BP Badges:** {basic_info.get('badgeCnt', 'N/A')}",
                inline=False
            )
            
            # Account Activity
            created_at = self.convert_unix_timestamp(int(basic_info.get('createAt', 0))) if basic_info.get('createAt') else "N/A"
            last_login = self.convert_unix_timestamp(int(basic_info.get('lastLoginAt', 0))) if basic_info.get('lastLoginAt') else "N/A"
            
            embed.add_field(
                name="📅 ACCOUNT ACTIVITY",
                value=f"**Created At:** {created_at}\n"
                      f"**Last Login:** {last_login}\n"
                      f"**Recent OB:** {basic_info.get('releaseVersion', 'N/A')}",
                inline=False
            )
            
            # Signature
            signature = social_info.get('signature', 'None')
            if signature and signature != 'None':
                embed.add_field(
                    name="💬 SIGNATURE",
                    value=f"*{signature}*",
                    inline=False
                )
            
            # GUILD STATS (if available)
            if clan_info:
                guild_info = f"**Name:** {clan_info.get('clanName', 'N/A')}\n" \
                            f"**ID:** `{clan_info.get('clanId', 'N/A')}`\n" \
                            f"**Level:** {clan_info.get('clanLevel', 'N/A')}\n" \
                            f"**Members:** {clan_info.get('memberNum', 'N/A')}/{clan_info.get('capacity', 'N/A')}"
                
                # Guild Leader Info (if available)
                if captain_info:
                    guild_info += f"\n**Leader:** {captain_info.get('nickname', 'N/A')} (UID: `{captain_info.get('accountId', 'N/A')}`)"
                
                embed.add_field(
                    name="🏰 GUILD INFORMATION",
                    value=guild_info,
                    inline=False
                )
            
            # Add a decorative footer
            embed.set_footer(text="Developed by Astral • Free Fire Stats", icon_url="https://i.imgur.com/6eQEsZP.png")
            
            await ctx.send(embed=embed)

            # Generate and send profile image
            try:
                image_url = f"{self.generate_url}?uid={uid}"
                async with self.session.get(image_url) as img_file:
                    if img_file.status == 200:
                        with io.BytesIO(await img_file.read()) as buf:
                            file = discord.File(buf, filename=f"profile_{uid}.png")
                            await ctx.send("**Character Profile:**", file=file)
            except Exception as e:
                print("Image generation failed:", e)

        except Exception as e:
            await ctx.send(f" Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def cog_unload(self):
        await self.session.close()

async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
