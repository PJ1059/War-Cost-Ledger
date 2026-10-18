-- Presentation-only notifications emitted at confirmed debit sites. No account
-- reads, persistence, game access, or reconstruction from cumulative totals.
local function clock(value)
    return type(value)=='number' and value>=0 and value<math.huge
end
local function cents(value)
    return clock(value) and value>0 and value%1==0
end

return function()
    local api={version=1,idle_seconds=2,revision=0,deadline=nil,max_named_items=8}
    local rows,by_key={},{}
    local last_now=0
    local cached,cached_revision,cached_visible
    local function timestamp(now)
        assert(clock(now),'charge notifications need a finite non-negative clock')
        last_now=math.max(last_now,now)
        return last_now
    end
    local function clear()
        rows,by_key={},{}
        api.deadline=nil
        api.revision=api.revision+1
    end
    function api:reset(now)
        if now~=nil then timestamp(now) end
        clear()
    end
    function api:update(now,shared_deadline)
        now=timestamp(now)
        -- Only an already active batch can be prolonged by new awards. Never
        -- revive a collected fee or manufacture one from an award notification.
        if self.deadline and clock(shared_deadline) and shared_deadline>now
            and shared_deadline>self.deadline then
            self.deadline=shared_deadline
            self.revision=self.revision+1
        end
        if self.deadline and now>=self.deadline then clear() end
        return self.revision
    end
    function api:emit(key,name,amount,now)
        if type(key)~='string' or key=='' or type(name)~='string' or name=='' or not cents(amount) then
            return false
        end
        now=timestamp(now)
        self:update(now)
        local row=by_key[key]
        if not row and #rows>=self.max_named_items then
            -- The final retained row sums overflow. Even sustained fire creates
            -- no per-shot objects and never an unbounded notification queue.
            key,name='__other_charges__','其他支出'
            row=by_key[key]
        end
        if not row then
            row={key=key,name=name,amount_cents=0,changed_at=now}
            rows[#rows+1]=row
            by_key[key]=row
        end
        row.amount_cents=row.amount_cents+amount
        row.changed_at=now
        self.deadline=now+self.idle_seconds
        self.revision=self.revision+1
        return true
    end
    function api:snapshot(now,visible,shared_deadline)
        self:update(now,shared_deadline)
        visible=visible==true
        if cached and cached_revision==self.revision and cached_visible==visible then return cached end
        local view={version=1,revision=self.revision,deadline=self.deadline,items={}}
        if visible then
            for index,row in ipairs(rows) do
                view.items[index]={key=row.key,name=row.name,amount_cents=row.amount_cents,changed_at=row.changed_at}
            end
        end
        cached,cached_revision,cached_visible=view,self.revision,visible
        return view
    end
    return api
end
