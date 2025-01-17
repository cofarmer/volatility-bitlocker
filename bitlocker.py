import volatility.plugins.common as common
import volatility.utils as utils
import volatility.obj as obj
import volatility.win32.tasks as tasks
from volatility.renderers import TreeGrid
from volatility.renderers.basic import Address
import volatility.poolscan as poolscan
import binascii

class MyPoolScan(poolscan.SinglePoolScanner):
    """ Pool scanner """

class Bitlocker(common.AbstractWindowsCommand):
    """Extract Bitlocker FVEK. Supports Windows 7 - 10."""
    def __init__(self, config, *args, **kwargs):
        common.AbstractWindowsCommand.__init__(self, config, *args, **kwargs)
    def calculate(self):
        PoolSize = {
        'Fvec128' : 508,
        'Fvec256' : 1008,
        'Cngb128' : 632,
        'Cngb256' : 672,
	'None128' : 1280,
	'None256' : 1500,
        #'Cngb128' : 2048,
        #'Cngb256' : 10240,
        }
        BLMode = {
        '00' : 'AES 128-bit with Diffuser',
        '01' : 'AES 256-bit with Diffuser',
        '02' : 'AES 128-bit',
        '03' : 'AES 256-bit',
        '10' : 'AES 128-bit (Win 8+)',
        '20' : 'AES 256-bit (Win 8+)',
        '40' : 'AES 256-bit (Win 10)'
       }

        length = 16

        address_space = utils.load_as(self._config)
        winver = (address_space.profile.metadata.get("major", 0), address_space.profile.metadata.get("minor", 0))
        arch = address_space.profile.metadata.get("memory_model",0)

	# Win7
        if winver < (6,2):
            tweak = "Not Applicable"
            poolsize = lambda x : x >= PoolSize['Fvec128'] and x <= PoolSize['Fvec256']
            scanner = MyPoolScan()
            scanner.checks = [
                ('PoolTagCheck', dict(tag = "FVEc")),
                ('CheckPoolSize', dict(condition = poolsize)),
                ('CheckPoolType', dict(paged = False, non_paged = True)),
                     ]
            # Only temporary until this can be fixed properly
            if (arch == '32bit'):
                modeOffsetRel = 0x18
                fvekOffsetRel = 0x20
                tweakOffsetRel = 0x1F8

            if (arch == '64bit'):
                modeOffsetRel = 0x2C
                fvekOffsetRel = 0x30
                tweakOffsetRel = 0x210

            for offset in scanner.scan(address_space):
                pool = obj.Object("_POOL_HEADER", offset = offset, vm = address_space)
                mode = address_space.zread(offset+modeOffsetRel,1)
	        for o, h, c in utils.Hexdump(mode):
                    mode =h

                if mode == '01' or mode == '03':
                    length = 32
                else:
                    length = 16
                fvek_raw = address_space.zread(offset+fvekOffsetRel,length)
                if mode == '01' or mode == '00':
		    tweak_raw = address_space.zread(offset+tweakOffsetRel,length)
                yield pool, BLMode[mode], tweak_raw, fvek_raw

	# Win8+, part of Win10
        if winver >= (6,2) and winver < (6,4):
            tweak = "Not Applicable"
            poolsize = lambda x : x >= PoolSize['Cngb128'] and x <= PoolSize['Cngb256']
            scanner = MyPoolScan()
            scanner.checks = [
                ('PoolTagCheck', dict(tag = "Cngb")),
                ('CheckPoolSize', dict(condition = poolsize)),
                ('CheckPoolType', dict(paged = False, non_paged = True)),
		]

		# Quick, hacky fix as a temporary solution.
		# https://pbs.twimg.com/media/Ce-B2sgXEAAqTQ_.jpg
            if (arch == '32bit'):
                modeOffsetRel = 0x5C
                fvek1OffsetRel = 0x60
                fvek2OffsetRel = 0x84

            if (arch == '64bit'):
                modeOffsetRel = 0x68
                fvek1OffsetRel = 0x6C
                fvek2OffsetRel = 0x90

            for offset in scanner.scan(address_space):
                pool = obj.Object("_POOL_HEADER", offset = offset, vm = address_space)
                mode = address_space.zread(offset+modeOffsetRel,1)
                for o, h, c in utils.Hexdump(mode):
                    mode =h

                if mode == '20':
                    length = 32
                else:
                    length = 16                 
                fvek_raw = address_space.zread(offset+fvek1OffsetRel,length)
                tweak_raw = address_space.zread(offset+fvek2OffsetRel,length)
                if fvek_raw == tweak_raw and fvek_raw != binascii.a2b_hex('0' * (length * 2)):
                    yield pool, BLMode[mode], tweak_raw, fvek_raw
	
	# >= Win10 18362
	if winver >= (6,4):
	    tweak = "Not Applicable"
            poolsize = lambda x : x >= PoolSize['None128'] and x <= PoolSize['None256']
            scanner = MyPoolScan()
            scanner.checks = [
                ('PoolTagCheck', dict(tag = "None")),
                ('CheckPoolSize', dict(condition = poolsize)),
                ('CheckPoolType', dict(paged = False, non_paged = True)),
		]

	    # 32bit system not supported 
            #if (arch == '32bit'):
            #    modeOffsetRel = 0x5C
            #    fvek1OffsetRel = 0x60
            #    fvek2OffsetRel = 0x84

            if (arch == '64bit'):
                modeOffsetRel = 0x98
                fvek1OffsetRel = 0x9C
                fvek2OffsetRel = 0xAC

            for offset in scanner.scan(address_space):
                pool = obj.Object("_POOL_HEADER", offset = offset, vm = address_space)
                mode = address_space.zread(offset+modeOffsetRel,1)
                for o, h, c in utils.Hexdump(mode):
                    mode =h

                if mode == '10':
                    length = 16
                elif mode == '20':
                    length = 16                 
	    	elif mode == '40':
		    length = 32
		    fvek2OffsetRel = 0xBC
                fvek_raw = address_space.zread(offset+fvek1OffsetRel,length)
                tweak_raw = address_space.zread(offset+fvek2OffsetRel,length)
                if fvek_raw != tweak_raw and fvek_raw != binascii.a2b_hex('0' * (length * 2)):
                    yield pool, BLMode[mode], tweak_raw, fvek_raw



    def unified_output(self, data):
        return TreeGrid([("Address", Address),
                                         ("Cipher", str),
                                         ("FVEK", str),
                                         ("TWEAK Key", str)
                                         ], self.generator(data))
    def generator(self, data):
        for (pool, BLMode, tweak_raw, fvek_raw) in data:
            fvek = []
	    tweak = []
            for o, h, c in utils.Hexdump(fvek_raw):
                fvek.append(h)
	    for o, h, c in utils.Hexdump(tweak_raw):
		tweak.append(h)
            yield(0, [Address(pool),BLMode, str(''.join(fvek).replace(" ","")), str(''.join(tweak).replace(" ","")),])
    def render_text(self, outfd, data):
        self.table_header(outfd, [("Address", "#018x"),
                                  ("Cipher", "32"),
                                  ("FVEK", "64"),
                                  ("TWEAK Key", "64"),
                                 ])
        for (pool, BLMode, tweak_raw, fvek_raw) in data:
            fvek = []
	    tweak = []
            for o, h, c in utils.Hexdump(fvek_raw):
                fvek.append(h)
            for o, h, c in utils.Hexdump(tweak_raw):
                tweak.append(h)
            self.table_row(outfd,
                           pool,
                           BLMode,
                           ''.join(fvek).replace(" ",""),
                           ''.join(tweak).replace(" ","")
                           )
